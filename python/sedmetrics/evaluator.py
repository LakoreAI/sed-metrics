"""Convenient entry point for the supported evaluation metrics."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from . import event, frame, psds, segment
from ._native import EventF1Result, PsdsResult, SegmentResult
from .dataset import Dataset


class SEDMetrics:
    """Evaluate events or scores using one discoverable entry point.

    ``eval`` returns the same structured result as the individual metric API.
    Pass a :class:`Dataset` as ``references`` to use recording and class names.
    Otherwise use integer IDs and supply ``recordings`` when required.
    """

    @staticmethod
    def eval(
        references: Dataset | Iterable[Any],
        predictions: Iterable[Any] | None = None,
        *,
        mode: str | None = None,
        metric: str | None = None,
        metrics: Sequence[str] | None = None,
        recordings: Mapping[int, float] | None = None,
        scores: Mapping[Any, Any] | Sequence[float] | None = None,
        metric_options: Mapping[str, Mapping[str, Any]] | None = None,
        **options: Any,
    ) -> EventF1Result | SegmentResult | PsdsResult | dict[str, Any]:
        """Evaluate one metric: ``event_f1`` (default), ``segment_f1`` or ``psds``.

        Pass ``metrics`` as a list to return a dictionary of results keyed by
        metric name, even for a one-item list. For multiple metrics, pass
        per-metric configuration as ``metric_options={name: {option: value}}``.
        The legacy ``metric`` argument returns one result object. Direct keyword
        options apply to the single-metric form only.
        PSDS requires ``scores``; event and segment metrics require predictions.
        Segment metrics and PSDS also require recording durations unless a
        :class:`Dataset` supplies them.

        With ``mode="frame"``, pass pre-aligned Boolean frame labels as
        ``references``, numeric frame scores as ``scores``, and the required
        ``threshold`` keyword. One class is evaluated. By default its confusion
        statistics and all frame metrics are returned; ``metrics`` can select
        a subset of precision, recall, f1, average_precision and auroc. Counts
        and configuration are always returned for auditing. ``boundaries`` and
        ``weighting`` are forwarded to :func:`sedmetrics.frame.evaluate`.
        """
        if mode not in (None, "frame"):
            raise ValueError("mode must be None or 'frame'")
        if mode == "frame":
            if isinstance(references, Dataset):
                raise ValueError("frame mode requires aligned Boolean labels, not a Dataset")
            if predictions is not None or recordings is not None:
                raise ValueError("frame mode uses references and scores, not predictions or recordings")
            if metric is not None or metric_options is not None:
                raise ValueError("frame mode accepts metric selection through metrics only")
            if scores is None or isinstance(scores, Mapping) or isinstance(scores, (str, bytes)):
                raise ValueError("frame mode requires a sequence of numeric scores")
            frame_metrics = ("precision", "recall", "f1", "average_precision", "auroc")
            if metrics is not None:
                if isinstance(metrics, (str, bytes)) or not isinstance(metrics, Sequence) or not metrics:
                    raise ValueError("metrics must be a nonempty sequence of frame metric names")
                if any(not isinstance(name, str) or name not in frame_metrics for name in metrics):
                    raise ValueError(f"unknown frame metric; choose from {frame_metrics}")
                if len(set(metrics)) != len(metrics):
                    raise ValueError("metrics must not contain duplicates")
            result = frame.evaluate(list(references), scores, **options)
            if metrics is not None:
                for name in frame_metrics:
                    if name not in metrics:
                        del result[name]
            return result
        available = ("event_f1", "segment_f1", "psds")
        if metrics is not None:
            if metric is not None:
                raise ValueError("use either metric or metrics, not both")
            if isinstance(metrics, (str, bytes)) or not isinstance(metrics, Sequence):
                raise ValueError("metrics must be a sequence of metric names")
            if not metrics:
                raise ValueError("metrics must not be empty")
            if any(not isinstance(name, str) or name not in available for name in metrics):
                raise ValueError(f"unknown metric in {metrics!r}; choose from {available}")
            if len(set(metrics)) != len(metrics):
                raise ValueError("metrics must not contain duplicates")
            if options:
                raise ValueError("use metric_options for options when metrics is supplied")
            configs = dict(metric_options or {})
            if set(configs) - set(metrics):
                raise ValueError("metric_options contains an unselected metric")
            if any(not isinstance(value, Mapping) for value in configs.values()):
                raise ValueError("each entry in metric_options must be a mapping")
            event_metrics = any(name != "psds" for name in metrics)
            if event_metrics and predictions is None:
                raise ValueError("event_f1 and segment_f1 require predictions")
            if "psds" in metrics and scores is None:
                raise ValueError("psds requires scores")
            if not event_metrics and predictions is not None:
                raise ValueError("predictions were supplied without an event metric")
            if "psds" not in metrics and scores is not None:
                raise ValueError("scores were supplied without a score-based metric")
            # Inputs can be generators: consume each once before evaluating
            # multiple metrics. Datasets already retain their references.
            refs = references if isinstance(references, Dataset) else list(references)
            preds = None if predictions is None else list(predictions)
            return {
                name: SEDMetrics.eval(
                    refs,
                    None if name == "psds" else preds,
                    metric=name,
                    recordings=recordings,
                    scores=scores if name == "psds" else None,
                    **dict(configs.get(name, {})),
                )
                for name in metrics
            }
        if metric_options is not None:
            raise ValueError("metric_options requires metrics")
        metric = "event_f1" if metric is None else metric
        if metric not in available:
            raise ValueError(f"unknown metric {metric!r}; choose event_f1, segment_f1 or psds")
        if isinstance(references, Dataset):
            if recordings is not None:
                raise ValueError("recordings are already supplied by the Dataset")
            if metric == "psds":
                if scores is None or predictions is not None:
                    raise ValueError("psds requires scores and does not accept predictions")
                return references.psds(scores, **options)
            if predictions is None or scores is not None:
                raise ValueError(f"{metric} requires predictions and does not accept scores")
            if metric == "event_f1":
                return references.event_f1(predictions, **options)
            return references.segment_f1(predictions, **options)
        if metric == "psds":
            if scores is None or recordings is None or predictions is not None:
                raise ValueError("psds requires scores and recordings, and does not accept predictions")
            return psds.psds(references, scores, recordings=recordings, **options)
        if predictions is None or scores is not None:
            raise ValueError(f"{metric} requires predictions and does not accept scores")
        if metric == "event_f1":
            return event.f1(references, predictions, recordings=recordings, **options)
        if recordings is None:
            raise ValueError("segment_f1 requires recordings")
        return segment.f1(references, predictions, recordings=recordings, **options)
