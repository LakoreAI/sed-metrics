"""Segment-based (frame-block) evaluation.

See ``docs/metrics/segment_f1.md`` for the specification.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol, Union

from ._native import ClassSegmentMetrics, SegmentResult, segment_f1 as _segment_f1

__all__ = ["ClassSegmentMetrics", "SegmentResult", "f1"]


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
    segment_length: float = 1.0,
    average: str = "micro",
    recordings: Mapping[int, float] | None = None,
) -> SegmentResult:
    """Compute segment-based precision, recall, F1 and S/D/I error counts.

    A segment ``[k * segment_length, (k + 1) * segment_length)`` is active for a
    class when any event of that class overlaps it; segment indices use
    ``floor(onset / length)`` and ``ceil(offset / length)``. Per segment, the
    reference and predicted class sets give TP/FP/FN and the
    substitution/deletion/insertion counts.

    Parameters
    ----------
    references, predictions:
        Iterables of events in the same spellings as :func:`sedmetrics.event.f1`.
    segment_length:
        Segment length in seconds (default 1.0, the DCASE baseline).
    average:
        ``"micro"`` (pool counts over classes, default) or ``"macro"`` (mean of
        per-class ratios over the classes where the ratio is defined).
    recordings:
        Optional ``{recording_id: duration_seconds}``. When given, a recording
        is evaluated over its full duration; otherwise over the latest event
        offset. Events outside their recording are rejected.

    Returns
    -------
    SegmentResult
        Precision/recall/F1, TP/FP/FN, ``n_substitutions``/``n_deletions``/
        ``n_insertions``, the error rate and its S/D/I decomposition, per-class
        statistics and the configuration used. Undefined ratios are ``None``.

    Notes
    -----
    ``error_rate = (S + D + I) / n_reference`` can exceed 1. A substitution
    produces one S but two class-level errors, so
    ``FP + FN = 2 S + D + I``; that identity is tested.

    Examples
    --------
    >>> import sedmetrics as sm
    >>> result = sm.segment.f1(
    ...     references=[(0, 0, 0.5, 1.5)],
    ...     predictions=[(0, 0, 0.6, 1.6)],
    ... )
    >>> round(result.f1, 6)
    1.0
    """
    return _segment_f1(
        references,
        predictions,
        segment_length=segment_length,
        average=average,
        recordings=None if recordings is None else dict(recordings),
    )
