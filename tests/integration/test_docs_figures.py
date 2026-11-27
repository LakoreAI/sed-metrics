"""The documentation figures must show what the library computes today."""

import importlib.util
from pathlib import Path

TOOL = Path(__file__).resolve().parents[2] / "tools" / "docs_figures.py"


def test_figures_match_the_library():
    spec = importlib.util.spec_from_file_location("docs_figures", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.stale_figures() == []
