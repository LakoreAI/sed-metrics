"""Reproducible evaluation reports.

``evaluate`` runs the requested metrics over a dataset and a prediction list and
returns a JSON-serialisable report: dataset identity, metric configurations,
counts and per-class statistics. ``read_event_table`` reads predictions from a
tab- or comma-separated file so a run can be evaluated from an artifact.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from . import __version__
from .dataset import Dataset

__all__ = [
    "EVENT_METRICS",
    "METRICS",
    "evaluate",
    "evaluate_file",
    "read_event_table",
    "write_report",
]

EVENT_METRICS = ("event_f1", "segment_f1")
METRICS = EVENT_METRICS + ("psds",)

_TABLE_ALIASES = {
    "recording": ("recording", "recording_id", "filename", "clip"),
    "class": ("class", "class_id", "event_label", "label"),
    "onset": ("onset", "event_onset", "start"),
    "offset": ("offset", "event_offset", "end"),
}


def _normalise_header(fieldnames: Sequence[str] | None, source: str) -> dict[str, str]:
    if not fieldnames:
        raise ValueError(f"{source}: missing header row")
    header = {name.strip(): name for name in fieldnames if name.strip()}
    resolved: dict[str, str] = {}
    for field, aliases in _TABLE_ALIASES.items():
        matches = [alias for alias in aliases if alias in header]
        if len(matches) != 1:
            raise ValueError(
                f"{source}: expected exactly one column for {field!r} "
                f"(one of {aliases}), found {matches}"
            )
        resolved[field] = header[matches[0]]
    return resolved


def read_event_table(path: str | Path) -> list[tuple[str, str, float, float]]:
    """Read predictions from a TSV/CSV file.

    The header names the four columns; accepted aliases are
    ``recording``/``recording_id``/``filename``/``clip``,
    ``class``/``class_id``/``event_label``/``label``,
    ``onset``/``event_onset``/``start`` and ``offset``/``event_offset``/``end``.
    Rows are returned as ``(recording, class, onset, offset)`` with names as
    strings; :meth:`sedmetrics.Dataset.encode` maps them to ids.

    The delimiter is a tab when the header contains one, otherwise a comma.
    Empty lines are ignored; a malformed row raises with its line number.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        first_line = handle.readline()
        handle.seek(0)
        delimiter = "\t" if "\t" in first_line else ","
        reader = csv.DictReader(handle, delimiter=delimiter)
        columns = _normalise_header(reader.fieldnames, str(path))

        events: list[tuple[str, str, float, float]] = []
        for line_number, row in enumerate(reader, start=2):
            if not any((value or "").strip() for value in row.values()):
                continue
            recording = (row.get(columns["recording"]) or "").strip()
            event_class = (row.get(columns["class"]) or "").strip()
            if not recording or not event_class:
                raise ValueError(
                    f"{path}:{line_number}: recording and class must be non-empty"
                )
            try:
                onset = float(row[columns["onset"]])
                offset = float(row[columns["offset"]])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{path}:{line_number}: non-numeric onset or offset"
                ) from error
            events.append((recording, event_class, onset, offset))
    return events


def evaluate(
    dataset: Dataset,
    predictions: Iterable[Any],
    *,
    scores: Mapping[Any, Any] | None = None,
    metrics: Iterable[str] = EVENT_METRICS,
    event_f1_kwargs: Mapping[str, Any] | None = None,
    segment_f1_kwargs: Mapping[str, Any] | None = None,
    psds_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate ``predictions`` and return a JSON-serialisable report.

    Parameters
    ----------
    dataset:
        Loaded reference data.
    predictions:
        Events using recording and class names or ids; unknown names raise.
    scores:
        Per-frame score tracks for ``"psds"``, in the form accepted by
        :func:`sedmetrics.psds.psds` (names or ids). Required only for PSDS.
    metrics:
        Subset of ``METRICS``: ``"event_f1"``, ``"segment_f1"`` and ``"psds"``.
    event_f1_kwargs, segment_f1_kwargs, psds_kwargs:
        Extra keyword arguments forwarded to the metric, for example
        ``{"onset_collar": 0.2}``, ``{"segment_length": 0.5}`` or
        ``{"dtc_threshold": 0.7}``.

    Returns
    -------
    dict
        ``{"sedmetrics_version", "dataset", "predictions", "metrics"}`` where
        each metric entry is the metric's ``to_dict()`` output: configuration,
        counts, ratios and per-class statistics. Undefined ratios are ``None``
        and the report is valid JSON with no ``NaN``.
    """
    from . import event, segment

    encoded = dataset.encode(predictions)
    report: dict[str, Any] = {
        "sedmetrics_version": __version__,
        "dataset": {
            "name": dataset.name,
            "source": dataset.source,
            "n_recordings": dataset.n_recordings,
            "n_events": dataset.n_events,
            "n_classes": dataset.n_classes,
        },
        "predictions": {"n_events": len(encoded)},
        "metrics": {},
    }

    for name in metrics:
        if name == "event_f1":
            result = event.f1(
                dataset.references,
                encoded,
                recordings=dataset.durations,
                **dict(event_f1_kwargs or {}),
            )
        elif name == "segment_f1":
            result = segment.f1(
                dataset.references,
                encoded,
                recordings=dataset.durations,
                **dict(segment_f1_kwargs or {}),
            )
        elif name == "psds":
            if scores is None:
                raise ValueError("the 'psds' metric requires per-frame scores")
            result = dataset.psds(scores, **dict(psds_kwargs or {}))
        else:
            raise ValueError(f"unknown metric {name!r}; available metrics: {METRICS}")
        report["metrics"][name] = result.to_dict()

    return report


def evaluate_file(
    dataset: Dataset,
    predictions_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Read predictions from a TSV/CSV file and evaluate them.

    Score-based metrics still need ``scores`` passed explicitly.
    """
    return evaluate(dataset, read_event_table(predictions_path), **kwargs)


def write_report(report: Mapping[str, Any], path: str | Path) -> Path:
    """Write a report as JSON (no NaN, deterministic key order)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path
