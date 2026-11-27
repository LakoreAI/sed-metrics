"""Experimental metrics for immutable CREATE-only alert logs."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from statistics import mean, median
from typing import Any

from .._native import streaming_create


def evaluate(references: Iterable[Any], alerts: Iterable[tuple[int, int, int, float, float, float | None]], *, recordings: Mapping[int, float], class_ids: Sequence[int], matching_window: float, deadlines: Sequence[float], horizon: float, clock: str) -> dict[str, Any]:
    """Evaluate immutable CREATE alerts using the experimental v1 protocol.

    Each alert is ``(recording_id, alert_id, class_id, emitted_at,
    audio_available_until, latest_audio_used)``. Times are seconds. ``clock``
    must explicitly be ``"measured"`` or ``"simulated"``; this label alone
    does not establish causality. Updates and cancellations are not accepted by
    this CREATE-only input format. See ``docs/streaming-protocol.md``.
    """
    if clock not in ("measured", "simulated"):
        raise ValueError("clock must be 'measured' or 'simulated'")
    result = streaming_create(list(references), list(alerts), dict(recordings), list(class_ids), matching_window, list(deadlines), horizon)
    delays = sorted(result["delays"])
    def percentile(p: float) -> float | None:
        if not delays:
            return None
        pos = p * (len(delays) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(delays) - 1)
        return delays[lo] + (delays[hi] - delays[lo]) * (pos - lo)
    result.update({"matching_window": matching_window, "class_ids": list(class_ids), "deadlines": list(deadlines), "horizon": horizon, "clock": clock,
                   "mean_delay": mean(delays) if delays else None, "median_delay": median(delays) if delays else None,
                   "p90_delay": percentile(0.90), "p95_delay": percentile(0.95),
                   "matched_recall": result["n_matched"] / result["n_observed"] if result["n_observed"] else None,
                   "specification": "streaming_create/1"})
    return result
