import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionPolicy:
    minimum_score: float | None = None
    minimum_margin: float | None = None
    require_consistency: bool = False

    def __post_init__(self):
        if not isinstance(self.require_consistency, bool):
            raise ValueError("require_consistency must be a boolean")
        for value in (self.minimum_score, self.minimum_margin):
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("Policy thresholds must be finite and between 0 and 1")

    def assess(self, score, margin, stable):
        reasons = []
        if self.minimum_score is not None and score < self.minimum_score:
            reasons.append("score_below_task_threshold")
        if self.minimum_margin is not None and margin < self.minimum_margin:
            reasons.append("margin_below_task_threshold")
        if self.require_consistency and stable is not True:
            reasons.append("consistency_not_established")
        configured = (
            self.minimum_score is not None
            or self.minimum_margin is not None
            or self.require_consistency
        )
        return ("escalate" if reasons else "accept" if configured else "review"), reasons
