"""PSDS (Polyphonic Sound Detection Score).

See ``docs/metrics/psds.md`` for the specification.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ._native import ClassPsds, PsdsResult, merge_psds as _merge_psds, psds as _psds

__all__ = ["ClassPsds", "PsdsResult", "PiPsdsResult", "psds", "pipsds"]

ScoreSeries = Mapping[Any, Sequence[float]]
"""``{class: per-frame scores}`` for one recording."""


@dataclass(frozen=True)
class PiPsdsResult:
    """Envelope result and the names of the supplied post-processings."""
    result: PsdsResult
    postprocessings: tuple[str, ...]

    @property
    def psds(self) -> float:
        return self.result.psds

    @property
    def classes(self):
        return self.result.classes

    @property
    def efpr(self) -> list[float]:
        return self.result.efpr

    @property
    def tpr(self) -> list[float]:
        return self.result.tpr

    @property
    def config(self) -> dict[str, Any]:
        return self.result.config

    @property
    def dataset_duration(self) -> float:
        return self.result.dataset_duration

    def to_dict(self) -> dict[str, Any]:
        return {**self.result.to_dict(), "postprocessings": list(self.postprocessings), "specification": "pipsds/1"}


def pipsds(references: Iterable[Any], processed_scores: Mapping[str, Mapping[Any, Any]], *, recordings: Mapping[Any, float], **kwargs: Any) -> PiPsdsResult:
    """Evaluate an envelope over explicitly supplied post-processed score tracks.

    Every named configuration must cover the same recordings and classes. The
    per-class upper envelope can select different configurations at different
    false-positive rates; it does not represent a single deployed policy. The
    caller is responsible for recording how each score track was produced and
    whether its processing is causal.
    """
    if not processed_scores:
        raise ValueError("at least one post-processing is required")
    if any(not isinstance(name, str) or not name for name in processed_scores):
        raise ValueError("post-processing names must be nonempty strings")
    refs = list(references)
    results = [psds(refs, scores, recordings=recordings, **kwargs) for scores in processed_scores.values()]
    return PiPsdsResult(_merge_psds(results), tuple(processed_scores))


def psds(
    references: Iterable[Any],
    scores: Mapping[Any, tuple[Sequence[float], ScoreSeries]],
    *,
    recordings: Mapping[Any, float],
    dtc_threshold: float = 0.7,
    gtc_threshold: float = 0.7,
    cttc_threshold: float | None = None,
    alpha_ct: float = 0.0,
    alpha_st: float = 1.0,
    max_efpr: float = 100.0,
    time_decimals: int = 6,
    unit: str = "hour",
) -> PsdsResult:
    """Compute PSDS with intersection-based DTC/GTC/CTTC criteria.

    The criteria are the intersection-based definitions used by
    ``sed_scores_eval``: a detection is DTC-relevant when its total intersection
    with same-class references covers ``dtc_threshold`` of its own length; a
    reference is a true positive when DTC-relevant detections cover
    ``gtc_threshold`` of its length; cross-triggers are DTC-failing detections
    that cover ``cttc_threshold`` of a reference of another class. There is no
    one-to-one assignment.

    Parameters
    ----------
    references:
        Reference events ``(recording_id, class_id, onset, offset)``, a mapping
        with those fields, or an object exposing them.
    scores:
        ``{recording_id: (boundaries, {class_id: per_frame_scores})}``.
        ``boundaries`` has one more entry than there are frames; frame ``i``
        covers ``[boundaries[i], boundaries[i+1])``. Scores must be finite and
        identical in length to the number of frames. Every scored class must
        have at least one reference event, and the class sets must match.
        Each recording needs a track spanning zero to its duration with all
        evaluated class columns, including recordings without references.
    recordings:
        ``{recording_id: duration_seconds}``; required, used for exposure and
        for the effective false-positive rate.
    dtc_threshold, gtc_threshold:
        Intersection criteria. DCASE PSDS1: 0.7 / 0.7; PSDS2: 0.1 / 0.1.
    cttc_threshold:
        Cross-trigger criterion; must be set iff ``alpha_ct > 0``.
    alpha_ct:
        Weight of the mean cross-trigger rate. DCASE PSDS1: 0, PSDS2: 0.5.
    alpha_st:
        Weight of the cross-class standard deviation. DCASE: 1.0.
    max_efpr:
        Upper limit of the effective false-positive rate (DCASE: 100).
    time_decimals:
        Rounding of criterion sums (reference implementation: 6).
    unit:
        ``"second"``, ``"minute"`` or ``"hour"`` for the eFPR.

    Returns
    -------
    PsdsResult
        Macro PSDS, the macro curve, per-class PSDS with per-class curves and
        the configuration used.

    Examples
    --------
    >>> import sedmetrics as sm
    >>> result = sm.psds.psds(
    ...     references=[(0, 0, 1.0, 2.0)],
    ...     scores={0: ([0.0, 1.0, 2.0], {0: [0.1, 0.9]})},
    ...     recordings={0: 2.0},
    ...     unit="second",
    ...     max_efpr=10.0,
    ... )
    >>> result.psds > 0.5
    True
    """
    tracks: list[tuple[int, list[int], list[float], list[float]]] = []
    for recording_id, payload in scores.items():
        boundaries, columns = payload
        class_ids = list(columns)
        series = [columns[class_id] for class_id in class_ids]
        lengths = {len(values) for values in series}
        if len(lengths) > 1:
            raise ValueError(
                f"recording {recording_id}: class score series have different lengths"
            )
        # Row-major [frames, classes] layout, as the Rust score track expects.
        flat = [float(value) for frame in zip(*series, strict=True) for value in frame]
        tracks.append(
            (
                recording_id,
                class_ids,
                [float(boundary) for boundary in boundaries],
                flat,
            )
        )

    return _psds(
        tracks,
        references,
        dict(recordings),
        dtc_threshold=dtc_threshold,
        gtc_threshold=gtc_threshold,
        cttc_threshold=cttc_threshold,
        alpha_ct=alpha_ct,
        alpha_st=alpha_st,
        max_efpr=max_efpr,
        time_decimals=time_decimals,
        unit=unit,
    )
