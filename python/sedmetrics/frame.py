"""Classification metrics for one explicitly aligned binary frame track."""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Any

from ._native import frame_binary


def evaluate(
    labels: Sequence[bool],
    scores: Sequence[float],
    *,
    threshold: float,
    boundaries: Sequence[float] | None = None,
    weighting: str = "frame",
) -> dict[str, Any]:
    """Return confusion statistics, precision, recall, F1, AP and AUROC.

    Labels are already aligned to scores for one class; no event-to-frame
    mapping is inferred. ``weighting='duration'`` requires boundaries in
    seconds. For ``weighting='frame'``, every frame counts once.
    """
    if any(not isinstance(label, bool) for label in labels):
        raise ValueError("labels must contain booleans")
    if weighting not in ("frame", "duration"):
        raise ValueError("weighting must be 'frame' or 'duration'")
    if boundaries is not None:
        if len(boundaries) != len(labels) + 1:
            raise ValueError("boundaries must have one more entry than labels")
        if any(not isfinite(x) or x < 0 for x in boundaries):
            raise ValueError("boundaries must be finite and nonnegative")
        weights = [b - a for a, b in zip(boundaries, boundaries[1:])]
        if any(w <= 0 or not isfinite(w) for w in weights):
            raise ValueError("boundaries must be strictly increasing")
    elif weighting == "duration":
        raise ValueError("duration weighting requires boundaries")
    else:
        weights = [1.0] * len(labels)
    if weighting == "frame":
        weights = [1.0] * len(labels)
    result = frame_binary(list(labels), list(scores), weights, threshold)
    result.update({"threshold": threshold, "weighting": weighting, "n_frames": len(labels), "specification": "frame_binary/1"})
    return result
