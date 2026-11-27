"""SEDMetrics: evaluation metrics for Sound Event Detection.

The computational core is written in Rust; this package is the Python façade.
Only metrics documented in ``docs/metrics`` are exposed.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("sedmetrics")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

from . import adapters, event, report, segment
from ._native import (
    ClassEventF1,
    ClassSegmentMetrics,
    EventF1Result,
    SegmentResult,
    ValidationError,
)
from .dataset import Dataset

__all__ = [
    "ClassEventF1",
    "ClassSegmentMetrics",
    "Dataset",
    "EventF1Result",
    "SegmentResult",
    "ValidationError",
    "__version__",
    "adapters",
    "event",
    "report",
    "segment",
]
