"""Optional held-out temperature fitting; never modifies pretrained weights.

Fitting is not evidence of calibration quality on a new distribution. Evaluate on
another split before using the adjusted scores to select action thresholds.
"""

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from .scoring import normalize


def task_key(decision):
    fields = {k: decision[k] for k in ("model", "question", "method")}
    fields["snapshot"] = decision.get("model_snapshot")
    fields["prompt_version"] = decision.get("prompt_version")
    fields["choices"] = sorted(x["choice"] for x in decision["choices"])
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class TemperatureCalibration:
    temperature: float
    task: str
    examples: int
    dataset_id: str

    def __post_init__(self):
        if (
            not math.isfinite(self.temperature)
            or self.temperature <= 0
            or self.examples < 2
            or not self.dataset_id
        ):
            raise ValueError("Invalid calibration artifact")

    @classmethod
    def fit(cls, decisions, labels, dataset_id):
        if len(decisions) != len(labels) or len(labels) < 2 or not dataset_id:
            raise ValueError("Need matching held-out decisions/labels and dataset provenance")
        key = task_key(decisions[0])
        if any(task_key(d) != key for d in decisions):
            raise ValueError("Calibration must be task/model/method specific")
        rows = []
        for d, label in zip(decisions, labels):
            _validate_distribution(d)
            names = [x["choice"] for x in d["choices"]]
            if label not in names:
                raise ValueError("Unknown held-out label")
            rows.append(
                ([math.log(max(x["score"], 1e-300)) for x in d["choices"]], names.index(label))
            )
        # Bounded scalar grid; no classifier head, training pipeline, or model updates.
        temperatures = [math.exp(-3 + i * 6 / 240) for i in range(241)]

        def loss(t):
            return sum(
                -math.log(max(normalize([x / t for x in row])[target], 1e-300))
                for row, target in rows
            ) / len(rows)

        return cls(min(temperatures, key=loss), key, len(rows), dataset_id)

    def apply(self, decision):
        _validate_distribution(decision)
        if task_key(decision) != self.task:
            raise ValueError("Calibration task/model mismatch")
        scores = normalize(
            [math.log(max(x["score"], 1e-300)) / self.temperature for x in decision["choices"]]
        )
        return {
            "choices": [
                dict(choice=x["choice"], score=s) for x, s in zip(decision["choices"], scores)
            ],
            "calibration": asdict(self),
            "score_meaning": "Held-out temperature-adjusted preference; validate calibration on the target distribution.",
        }


def _validate_distribution(decision):
    scores = [x["score"] for x in decision["choices"]]
    if (
        not scores
        or any(not math.isfinite(x) or not 0 <= x <= 1 for x in scores)
        or not math.isclose(sum(scores), 1.0, abs_tol=1e-8)
    ):
        raise ValueError("Invalid decision score distribution")
