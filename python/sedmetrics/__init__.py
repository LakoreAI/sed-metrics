"""SEDMetrics: evaluation metrics for Sound Event Detection.

The computational core is written in Rust; this package is the Python façade.
Only metrics documented in ``docs/metrics`` are exposed.
"""

from importlib.metadata import PackageNotFoundError, version

from . import event
from ._native import ClassEventF1, EventF1Result, ValidationError

try:
    __version__ = version("sedmetrics")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "ClassEventF1",
    "EventF1Result",
    "ValidationError",
    "__version__",
    "event",
]
