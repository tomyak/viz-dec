import hashlib
import threading
import time
from dataclasses import dataclass

from .cache import VisualCache
from .image import load_image
from .policy import DecisionPolicy
from .scoring import aggregate, rotations, validate
from .timing import timed_execution

METHODS = ("label", "label_permute", "label_logmean", "candidate", "candidate_permute")


@dataclass(frozen=True)
class DecisionQuestion:
    question: str
    choices: list[str]


class ImageSession:
    def __init__(self, analyzer, path):
        self.analyzer, self.path = analyzer, path

    def classify(self, question, choices, **kwargs):
        return self.analyzer.classify_image(self.path, question, choices, **kwargs)


class Analyzer:
    def __init__(
        self,
        model=None,
        *,
        backend=None,
        cache_entries=4,
        cache_bytes=256 * 1024 * 1024,
        roots=None,
    ):
        if backend is None:
            from .models.gemma import DEFAULT_MODEL, GemmaBackend

            backend = GemmaBackend(model or DEFAULT_MODEL)
        self.backend = backend
        self.cache = VisualCache(cache_entries, cache_bytes)
        self.roots = roots
        self.lock = threading.RLock()

    def open_image(self, path):
        # Eager validation; sessions reread/hash to detect overwritten screenshots.
        load_image(path, self.roots)
        return ImageSession(self, path)

    def _state(self, image, key):
        state = self.cache.get(key)
        hit = state is not None
        if not hit:
            state, size = self.backend.encode(image)
            self.cache.put(key, state, size)
        return state, hit

    def _decide(self, state, question, choices, method, policy, hit):
        if method not in METHODS:
            raise ValueError(f"Method must be one of {METHODS}")
        start = time.perf_counter()
        orders = (
            rotations(len(choices))
            if method in ("label_permute", "label_logmean", "candidate_permute")
            else [list(range(len(choices)))]
        )
        raw, diagnostics = [], []
        for order in orders:
            scores, diag = self.backend.score(state, question, [choices[i] for i in order], method)
            raw.append(scores)
            diagnostics.append(diag)
        scores, agreement = aggregate(
            raw, orders, "logmean" if method == "label_logmean" else "mean"
        )
        ranked = sorted(zip(choices, scores), key=lambda x: (-x[1], x[0]))
        margin = ranked[0][1] - ranked[1][1]
        stable = (agreement == 1.0 and margin > 1e-12) if len(orders) > 1 else None
        action, reasons = policy.assess(ranked[0][1], margin, stable)
        return dict(
            model_snapshot=getattr(self.backend, "identity", None),
            prompt_version="decision-v1",
            model=getattr(self.backend, "name", type(self.backend).__name__),
            question=question,
            winner=ranked[0][0],
            score=ranked[0][1],
            choices=[dict(choice=c, score=s) for c, s in ranked],
            margin=margin,
            stable=stable,
            permutation_agreement=agreement if len(orders) > 1 else None,
            recommended_action=action,
            reasons=reasons,
            method=method,
            passes=len(orders),
            latency_ms=1000 * (time.perf_counter() - start),
            cache_hit=hit,
            diagnostics=diagnostics,
            score_meaning="Normalized model preference; not calibrated probability.",
        )

    @timed_execution
    def classify_image(self, image, question, choices, *, method="label_permute", policy=None):
        question, choices = validate(question, choices)
        if method not in METHODS:
            raise ValueError("Unknown scoring method")
        with self.lock:
            rgb, key = load_image(image, self.roots)
            state, hit = self._state(rgb, key)
            return self._decide(state, question, choices, method, policy or DecisionPolicy(), hit)

    classify = classify_image

    @timed_execution
    def inspect_image(self, image, questions, *, method="label_permute", policy=None):
        if not isinstance(questions, (list, tuple)) or not 1 <= len(questions) <= 32:
            raise ValueError("Expected 1–32 questions")
        if any(not isinstance(q, (DecisionQuestion, dict)) for q in questions):
            raise ValueError("Each question must be a DecisionQuestion or mapping")
        if any(isinstance(q, dict) and set(q) != {"question", "choices"} for q in questions):
            raise ValueError("Each question requires exactly question and choices")
        checked = [
            validate(q.question, q.choices)
            if isinstance(q, DecisionQuestion)
            else validate(q["question"], q["choices"])
            for q in questions
        ]
        if method not in METHODS:
            raise ValueError("Unknown scoring method")
        with self.lock:
            rgb, key = load_image(image, self.roots)
            state, hit = self._state(rgb, key)
            return {
                "decisions": [
                    self._decide(state, q, c, method, policy or DecisionPolicy(), hit or i > 0)
                    for i, (q, c) in enumerate(checked)
                ]
            }

    @timed_execution
    def classify_frame(self, rgb, question, choices, **kwargs):
        question, choices = validate(question, choices)
        method = kwargs.get("method", "label_permute")
        if method not in METHODS:
            raise ValueError("Unknown scoring method")
        from .image import MAX_PIXELS

        if rgb.width * rgb.height > MAX_PIXELS or rgb.mode != "RGB":
            raise ValueError("Expected a bounded RGB frame")
        key = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
        with self.lock:
            state, hit = self._state(rgb, key)
            return self._decide(
                state,
                question,
                choices,
                kwargs.get("method", "label_permute"),
                kwargs.get("policy") or DecisionPolicy(),
                hit,
            )

    @timed_execution
    def analyze_video(self, path, question, choices, sample_interval=1.0, **kwargs):
        from .video import analyze_video

        return analyze_video(self, path, question, choices, sample_interval, **kwargs)

    @timed_execution
    def analyze_batch(self, **kwargs):
        from .batch import analyze_batch

        return analyze_batch(self, **kwargs)

    def info(self):
        with self.lock:
            return {**self.backend.info(), "cache": self.cache.info(), "local_only": True}

    @timed_execution
    def model_health(self):
        """Exercise fresh vision encoding and scoring without user files or cache hits."""
        from PIL import Image

        start = time.perf_counter()
        checks = []
        with self.lock:
            for expected, color in (("Red", (255, 0, 0)), ("Blue", (0, 0, 255))):
                state, _ = self.backend.encode(Image.new("RGB", (256, 256), color))
                decision = self._decide(
                    state,
                    "What is the dominant color in this image?",
                    ["Red", "Green", "Blue"],
                    "label_permute",
                    DecisionPolicy(),
                    False,
                )
                checks.append({"expected": expected, "decision": decision})
            ok = all(
                check["decision"]["winner"] == check["expected"] and check["decision"]["stable"]
                for check in checks
            )
            return {
                "status": "ok" if ok else "error",
                "checks": checks,
                "model": self.info(),
                "latency_ms": 1000 * (time.perf_counter() - start),
                "scope": "Synthetic vision/scoring smoke test; not task accuracy certification.",
            }
