"""Bounded media batches with shared visual encodes and request-scoped decision reuse."""

import copy
import hashlib
import os
from collections import OrderedDict
from pathlib import Path

from .image import load_image
from .policy import DecisionPolicy
from .scoring import validate

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}


def check_questions(questions):
    if not isinstance(questions, (list, tuple)) or not 1 <= len(questions) <= 32:
        raise ValueError("Expected 1–32 questions per media file")
    checked = []
    for item in questions:
        if not isinstance(item, dict) or set(item) != {"question", "choices"}:
            raise ValueError("Each question requires exactly question and choices")
        q, choices = validate(item["question"], item["choices"])
        checked.append({"question": q, "choices": choices})
    return checked


class BatchScorer:
    """One encode per distinct RGB frame; a bounded LRU avoids repeated question passes.

    No MLX tensors are retained in this memo. The analyzer owns a separate byte-bounded
    visual cache. Model operations remain serialized, avoiding parallel GPU allocations.
    """

    def __init__(self, analyzer, method="label_permute", policy=None, memo_entries=2048):
        from .classifier import METHODS

        if method not in METHODS:
            raise ValueError("Unknown scoring method")
        self.analyzer, self.method, self.policy = analyzer, method, policy or DecisionPolicy()
        self.memo = OrderedDict()
        self.memo_entries = memo_entries
        self.stats = dict(
            vision_encodes=0, vision_cache_hits=0, scoring_passes=0, decisions_reused=0
        )

    def inspect(self, rgb, questions):
        digest = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
        results, state, hit = [], None, False
        with self.analyzer.lock:
            for item in questions:
                key = (digest, item["question"], tuple(item["choices"]))
                if key in self.memo:
                    self.memo.move_to_end(key)
                    result = copy.deepcopy(self.memo[key])
                    result.update(decision_reused=True, latency_ms=0.0)
                    self.stats["decisions_reused"] += 1
                else:
                    if state is None:
                        state, hit = self.analyzer._state(rgb, digest)
                        self.stats["vision_cache_hits" if hit else "vision_encodes"] += 1
                    result = self.analyzer._decide(
                        state, item["question"], item["choices"], self.method, self.policy, hit
                    )
                    self.stats["scoring_passes"] += result["passes"]
                    result["decision_reused"] = False
                    self.memo[key] = copy.deepcopy(result)
                    if len(self.memo) > self.memo_entries:
                        self.memo.popitem(last=False)
                    hit = True
                results.append(result)
        return results


def discover(folder, recursive, roots, max_files):
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("folder must name a directory")
    if roots and not any(root.is_relative_to(Path(r).expanduser().resolve()) for r in roots):
        raise PermissionError("Folder is outside allowed roots")
    paths = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".")) if recursive else []
        for name in sorted(files):
            path = Path(directory) / name
            if not name.startswith(".") and path.suffix.lower() in IMAGE_SUFFIXES | VIDEO_SUFFIXES:
                paths.append(str(path))
                if len(paths) > max_files:
                    raise ValueError(
                        f"Folder exceeds max_files={max_files}; narrow the folder or raise the limit"
                    )
    return paths


def analyze_batch(
    analyzer,
    *,
    files=None,
    folder=None,
    questions=None,
    recursive=False,
    sample_interval=1.0,
    max_frames=300,
    max_total_frames=1000,
    max_files=128,
    max_decisions=4096,
    method="label_permute",
    policy=None,
):
    if (files is None) == (folder is None):
        raise ValueError("Supply exactly one of files or folder")
    for name, value, maximum in [
        ("max_files", max_files, 512),
        ("max_frames", max_frames, 1000),
        ("max_total_frames", max_total_frames, 10000),
        ("max_decisions", max_decisions, 16384),
    ]:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(f"{name} must be 1–{maximum}")
    if not isinstance(recursive, bool):
        raise ValueError("recursive must be a boolean")
    if folder is not None:
        files = discover(folder, recursive, analyzer.roots, max_files)
    if not isinstance(files, (list, tuple)) or not 1 <= len(files) <= max_files:
        raise ValueError(f"Expected 1–{max_files} media files")
    shared = check_questions(questions) if questions is not None else None
    plan = []
    for item in files:
        item = {"path": item} if isinstance(item, (str, Path)) else item
        if not isinstance(item, dict) or set(item) - {"path", "questions"} or "path" not in item:
            raise ValueError(
                "Each file must be a path or an object with path and optional questions"
            )
        if not isinstance(item["path"], (str, Path)) or not str(item["path"]):
            raise ValueError("File paths must be nonempty strings")
        selected = (
            check_questions(item["questions"]) if item.get("questions") is not None else shared
        )
        if selected is None:
            raise ValueError("Every file needs questions, either shared or per-file")
        plan.append((str(item["path"]), selected))
    # Validate the complete plan before the first decode or encode.
    from .video import analyze_video_questions, validate_video_options

    validate_video_options(sample_interval, max_frames, False, 0.0)
    scorer = BatchScorer(analyzer, method, policy)
    results, remaining_frames, remaining_decisions = [], max_total_frames, max_decisions
    for path, selected in plan:
        try:
            kind = "video" if Path(path).suffix.lower() in VIDEO_SUFFIXES else "image"
            if remaining_decisions < len(selected) or (kind == "video" and remaining_frames < 1):
                results.append(dict(path=path, status="skipped", reason="batch_budget_exhausted"))
                continue
            if kind == "video":
                cap = min(max_frames, remaining_frames, remaining_decisions // len(selected))
                remaining_frames -= cap
                remaining_decisions -= cap * len(selected)
                value = analyze_video_questions(
                    analyzer, path, selected, sample_interval, max_frames=cap, scorer=scorer
                )
                remaining_frames += cap - len(value["samples"])
                remaining_decisions += (cap - len(value["samples"])) * len(selected)
            else:
                remaining_decisions -= len(selected)
                rgb, _ = load_image(path, analyzer.roots)
                value = {"decisions": scorer.inspect(rgb, selected)}
            results.append(dict(path=path, kind=kind, status="ok", result=value))
        except (OSError, ValueError, RuntimeError) as exc:
            results.append(dict(path=path, status="error", error=str(exc)))
    return dict(
        results=results,
        summary=dict(
            files=len(results),
            succeeded=sum(r["status"] == "ok" for r in results),
            failed=sum(r["status"] == "error" for r in results),
            skipped=sum(r["status"] == "skipped" for r in results),
            frame_budget_used=max_total_frames - remaining_frames,
            decision_budget_used=max_decisions - remaining_decisions,
            **scorer.stats,
        ),
    )
