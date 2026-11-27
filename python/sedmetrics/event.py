"""Collar-based event evaluation.

See ``docs/metrics/event_f1.md`` for the specification.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol, Union

from ._native import ClassEventF1, EventF1Result, event_f1 as _event_f1

__all__ = ["ClassEventF1", "EventF1Result", "f1"]


class EventRecord(Protocol):
    """Anything exposing the four event fields as attributes."""

    recording_id: int
    class_id: int
    onset: float
    offset: float


EventInput = Union[Sequence[float], Mapping[str, Any], EventRecord]
"""Accepted event spellings: a 4-item sequence, a mapping or an object."""


def f1(
    references: Iterable[EventInput],
    predictions: Iterable[EventInput],
    *,
    onset_collar: float = 0.2,
    offset_collar: float = 0.2,
    offset_ratio: float = 0.2,
    evaluate_offset: bool = True,
    average: str = "micro",
    recordings: Mapping[int, float] | None = None,
) -> EventF1Result:
    """Compute collar-based event precision, recall and F1.

    A prediction matches a reference when the recording and class agree, the
    onset difference is at most ``onset_collar``, and (when ``evaluate_offset``)
    the offset difference is at most
    ``max(offset_collar, offset_ratio * reference_duration)``. Matching is
    one-to-one and maximum-cardinality per recording and class.

    Parameters
    ----------
    references, predictions:
        Iterables of events. Each event is ``(recording_id, class_id, onset,
        offset)``, a mapping with those keys, or an object exposing them. Times
        are seconds; intervals are half-open ``[onset, offset)``.
    onset_collar, offset_collar:
        Absolute tolerances in seconds (default 0.2).
    offset_ratio:
        Offset tolerance as a fraction of the reference duration (default 0.2).
    evaluate_offset:
        Set to ``False`` for a documented onset-only protocol.
    average:
        ``"micro"`` (pool counts over classes, default) or ``"macro"`` (mean
        over the classes where the ratio is defined).
    recordings:
        Optional ``{recording_id: duration_seconds}``. When given, events that
        extend past their recording or reference an unknown recording are
        rejected with :class:`sedmetrics.ValidationError`.

    Returns
    -------
    EventF1Result
        Ratios, counts, per-class statistics and the configuration used.
        Undefined ratios are ``None``.

    Examples
    --------
    >>> import sedmetrics as sm
    >>> result = sm.event.f1(
    ...     references=[(0, 0, 0.0, 1.0)],
    ...     predictions=[(0, 0, 0.05, 1.02)],
    ... )
    >>> round(result.f1, 6)
    1.0
    """
    return _event_f1(
        references,
        predictions,
        onset_collar=onset_collar,
        offset_collar=offset_collar,
        offset_ratio=offset_ratio,
        evaluate_offset=evaluate_offset,
        average=average,
        recordings=None if recordings is None else dict(recordings),
    )
