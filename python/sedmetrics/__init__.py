"""SEDMetrics: evaluation metrics for Sound Event Detection.

The computational core is written in Rust; this package is the Python façade.
Only metrics documented in ``docs/metrics`` are exposed.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sedmetrics")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

from . import adapters, event, frame, psds, report, segment
from ._native import (
    ClassEventF1,
    ClassPsds,
    ClassSegmentMetrics,
    EventF1Result,
    PsdsResult,
    SegmentResult,
    ValidationError,
)
from .dataset import Dataset
from .evaluator import SEDMetrics

__all__ = [
    "ClassEventF1",
    "ClassPsds",
    "ClassSegmentMetrics",
    "Dataset",
    "EventF1Result",
    "PsdsResult",
    "SegmentResult",
    "SEDMetrics",
    "ValidationError",
    "__version__",
    "adapters",
    "event",
    "frame",
    "psds",
    "report",
    "segment",
]
