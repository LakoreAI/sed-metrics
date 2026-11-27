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

class ValidationError(ValueError): ...

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
