"""Entry point for ``python -m sedmetrics``."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
