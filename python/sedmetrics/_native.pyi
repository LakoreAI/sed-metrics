from collections.abc import Iterable, Mapping
from typing import Any

class ClassEventF1:
    class_id: int
    n_reference: int
    n_predicted: int
    n_correct: int
    n_insertions: int
    n_deletions: int
    precision: float | None
    recall: float | None
    f1: float | None
    mean_onset_error: float | None
    mean_offset_error: float | None
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class EventF1Result:
    average: str
    n_reference: int
    n_predicted: int
    n_correct: int
    n_insertions: int
    n_deletions: int
    precision: float | None
    recall: float | None
    f1: float | None
    mean_onset_error: float | None
    mean_offset_error: float | None
    n_classes: int
    @property
    def classes(self) -> list[ClassEventF1]: ...
    @property
    def config(self) -> dict[str, Any]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class ClassSegmentMetrics:
    class_id: int
    n_true_positive: int
    n_false_positive: int
    n_false_negative: int
    n_reference: int
    n_predicted: int
    precision: float | None
    recall: float | None
    f1: float | None
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class SegmentResult:
    average: str
    n_true_positive: int
    n_false_positive: int
    n_false_negative: int
    n_reference: int
    n_predicted: int
    precision: float | None
    recall: float | None
    f1: float | None
    n_substitutions: int
    n_deletions: int
    n_insertions: int
    error_rate: float | None
    substitution_rate: float | None
    deletion_rate: float | None
    insertion_rate: float | None
    n_segments: int
    n_classes: int
    @property
    def classes(self) -> list[ClassSegmentMetrics]: ...
    @property
    def config(self) -> dict[str, Any]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class ClassPsds:
    class_id: int
    n_reference: int
    reference_duration: float
    psds: float
    efpr: list[float]
    tpr: list[float]
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class PsdsResult:
    psds: float
    dataset_duration: float
    efpr: list[float]
    tpr: list[float]
    @property
    def classes(self) -> list[ClassPsds]: ...
    @property
    def config(self) -> dict[str, Any]: ...
    def to_dict(self) -> dict[str, Any]: ...
    def __repr__(self) -> str: ...

class ValidationError(ValueError): ...

def psds(
    tracks: list[tuple[int, list[int], list[float], list[float]]],
    references: Iterable[Any],
    recordings: Mapping[int, float],
    *,
    dtc_threshold: float = 0.7,
    gtc_threshold: float = 0.7,
    cttc_threshold: float | None = None,
    alpha_ct: float = 0.0,
    alpha_st: float = 1.0,
    max_efpr: float = 100.0,
    time_decimals: int = 6,
    unit: str = "hour",
) -> PsdsResult: ...

def segment_f1(
    references: Iterable[Any],
    predictions: Iterable[Any],
    *,
    segment_length: float = 1.0,
    average: str | None = None,
    recordings: Mapping[int, float] | None = None,
) -> SegmentResult: ...

def event_f1(
    references: Iterable[Any],
    predictions: Iterable[Any],
    *,
    onset_collar: float = 0.2,
    offset_collar: float = 0.2,
    offset_ratio: float = 0.2,
    evaluate_offset: bool = True,
    average: str | None = None,
    recordings: Mapping[int, float] | None = None,
) -> EventF1Result: ...
def frame_binary(labels: list[bool], scores: list[float], weights: list[float], threshold: float) -> dict: ...
def brier_score(targets: list[float], probabilities: list[float], weights: list[float]) -> dict: ...
def merge_psds(results: list[PsdsResult]) -> PsdsResult: ...
def streaming_create(references: Any, alerts: list[tuple[int, int, int, float, float, float | None]], recordings: dict[int, float], class_ids: list[int], window: float, deadlines: list[float], horizon: float) -> dict: ...
def frame_labels(references: Any, recording_id: int, duration: float, class_id: int, boundaries: list[float]) -> list[bool]: ...
