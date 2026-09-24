"""Wire schemas shared by transport adapters, never by the core engine."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    question: str = Field(min_length=1, max_length=4096)
    choices: list[str] = Field(min_length=2, max_length=10)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    minimum_score: float | None = Field(default=None, ge=0, le=1)
    minimum_margin: float | None = Field(default=None, ge=0, le=1)
    require_consistency: bool = False


class BaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=4096)
    method: Literal["label", "label_permute", "label_logmean", "candidate", "candidate_permute"] = (
        "label_permute"
    )
    policy: Policy = Field(default_factory=Policy)


class ClassifyRequest(BaseRequest, Question):
    pass


class InspectRequest(BaseRequest):
    questions: list[Question] = Field(min_length=1, max_length=32)


class VideoRequest(ClassifyRequest):
    sample_interval: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    max_frames: int = Field(default=300, ge=1, le=1000)
    suppress_duplicates: bool = False
    similarity_threshold: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=4096)
    questions: list[Question] | None = Field(default=None, min_length=1, max_length=32)


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    files: list[str | MediaItem] | None = Field(default=None, min_length=1, max_length=512)
    folder: str | None = Field(default=None, min_length=1, max_length=4096)
    questions: list[Question] | None = Field(default=None, min_length=1, max_length=32)
    recursive: bool = False
    sample_interval: float = Field(default=1.0, gt=0, allow_inf_nan=False)
    max_frames: int = Field(default=300, ge=1, le=1000)
    max_total_frames: int = Field(default=1000, ge=1, le=10000)
    max_files: int = Field(default=128, ge=1, le=512)
    max_decisions: int = Field(default=4096, ge=1, le=16384)
    method: Literal["label", "label_permute", "label_logmean", "candidate", "candidate_permute"] = (
        "label_permute"
    )
    policy: Policy = Field(default_factory=Policy)
