"""Classification metrics for one explicitly aligned binary frame track."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from math import isfinite
from typing import Any

from ._native import brier_score, frame_binary, frame_labels
from .dataset import _unpack


def events(
    references: Iterable[Any],
    scores: Mapping[int, tuple[Sequence[float], Mapping[int, Sequence[float]]]],
    *, recordings: Mapping[int, float], threshold: float, weighting: str = "frame",
) -> dict[str, Any]:
    """Evaluate multi-class score tracks against event intervals.

    Every recording must have a full-duration score track with identical,
    explicit class columns. A frame is active if it has positive overlap with
    any same-class reference event. Returns per-class, micro and macro results.
    """
    refs = [_unpack(event, index) for index, event in enumerate(references)]
    if not recordings or set(scores) != set(recordings):
        raise ValueError("scores must contain exactly one track per recording")
    if any(r not in recordings for r, _, _, _ in refs):
        raise ValueError("reference contains an unknown recording")
    vocab: set[int] | None = None
    labels_by_class: dict[int, list[bool]] = {}
    scores_by_class: dict[int, list[float]] = {}
    weights_by_class: dict[int, list[float]] = {}
    for recording_id, (boundaries, columns) in scores.items():
        classes = set(columns)
        if not classes or (vocab is not None and classes != vocab):
            raise ValueError("every track must contain the same nonempty class vocabulary")
        vocab = classes
        weights = _weights(len(boundaries) - 1, boundaries, weighting)
        for class_id, series in columns.items():
            if len(series) != len(weights):
                raise ValueError("score series length must match frame count")
            labels = frame_labels(refs, recording_id, recordings[recording_id], class_id, list(boundaries))
            labels_by_class.setdefault(class_id, []).extend(labels)
            scores_by_class.setdefault(class_id, []).extend(series)
            weights_by_class.setdefault(class_id, []).extend(weights)
    if any(c not in vocab for _, c, _, _ in refs):
        raise ValueError("reference contains a class absent from the score vocabulary")
    classes = {c: frame_binary(labels_by_class[c], scores_by_class[c], weights_by_class[c], threshold) for c in sorted(vocab)}
    labels = [x for c in sorted(vocab) for x in labels_by_class[c]]
    values = [x for c in sorted(vocab) for x in scores_by_class[c]]
    weights = [x for c in sorted(vocab) for x in weights_by_class[c]]
    micro = frame_binary(labels, values, weights, threshold)
    names = ("precision", "recall", "f1", "average_precision", "auroc")
    macro = {}
    for name in names:
        defined = [result[name] for result in classes.values() if result[name] is not None]
        macro[name] = sum(defined) / len(defined) if defined else None
    return {"classes": classes, "micro": micro, "macro": macro, "threshold": threshold,
            "weighting": weighting, "mapping": "any_positive_overlap", "specification": "frame_events/1"}


def _weights(n: int, boundaries: Sequence[float] | None, weighting: str) -> list[float]:
    if weighting not in ("frame", "duration"):
        raise ValueError("weighting must be 'frame' or 'duration'")
    if boundaries is not None:
        if len(boundaries) != n + 1:
            raise ValueError("boundaries must have one more entry than labels")
        if any(not isfinite(x) or x < 0 for x in boundaries):
            raise ValueError("boundaries must be finite and nonnegative")
        weights = [b - a for a, b in zip(boundaries, boundaries[1:])]
        if any(w <= 0 or not isfinite(w) for w in weights):
            raise ValueError("boundaries must be strictly increasing")
    elif weighting == "duration":
        raise ValueError("duration weighting requires boundaries")
    else:
        weights = [1.0] * n
    return [1.0] * n if weighting == "frame" else weights


def brier(
    targets: Sequence[float], probabilities: Sequence[float], *,
    boundaries: Sequence[float] | None = None, weighting: str = "frame",
) -> dict[str, Any]:
    """Mean squared difference from aligned binary or soft targets for one class.

    Inputs must be probabilities in [0, 1]. No sigmoid or event-to-frame
    conversion is applied. A soft target represents the stated target probability;
    see ``docs/metrics/brier.md`` for its interpretation and limitations.
    """
    weights = _weights(len(targets), boundaries, weighting)
    result = brier_score(list(targets), list(probabilities), weights)
    result.update({"weighting": weighting, "n_frames": len(targets), "specification": "brier/1"})
    return result


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
    weights = _weights(len(labels), boundaries, weighting)
    result = frame_binary(list(labels), list(scores), weights, threshold)
    result.update({"threshold": threshold, "weighting": weighting, "n_frames": len(labels), "specification": "frame_binary/1"})
    return result
