---
title: "Develop and test SEDMetrics"
description: "Build the extension, run Rust and Python tests, check reference parity, regenerate the documentation figures and build the site."
---

# Development and validation

Install Rust 1.85 or newer and Python 3.10 or newer. Create a virtual
environment, install maturin and the test dependencies, then build the extension:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install maturin '.[test]'
maturin develop --release
```

## Checks

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p sedmetrics-core
python -m pytest
```

## Reference parity

Install `.[parity]` to run selected comparisons against pinned `sed_eval`,
`sed_scores_eval`, and scikit-learn versions. Dataset-dependent cases need
`SEDMETRICS_RAW_DATA` and skip when their files are unavailable. The comparison
fixtures do not establish parity for every possible input.

To point the suite at local dataset samples and use a separate oracle
environment:

```bash
uv venv --python 3.12 .venv-oracle
uv pip install --python .venv-oracle/bin/python pytest pyarrow "sedmetrics[parity]" \
    --find-links dist
maturin build --release -o dist && uv pip install --python .venv-oracle/bin/python \
    --force-reinstall dist/*.whl
SEDMETRICS_RAW_DATA=/path/to/data/raw .venv-oracle/bin/python -m pytest tests/parity
```

Parity runs use synthetic predictions derived from references, on sampled
URBAN-SED and AudioSet Strong clips. They are not a benchmark of any system.

!!! deviation "Current behaviour: a broken SciPy stops the run"

    The `sed_eval` and `sed_scores_eval` suites skip when their oracle cannot be
    imported. The frame and Brier suites skip only when scikit-learn is missing:
    if it is installed on a SciPy that fails to load, collection errors and
    `python -m pytest` stops. Run `python -m pytest tests/unit tests/integration`
    there, and the parity suite from a separate environment.

## Documentation

The figures draw numbers computed by the library. After changing a metric,
regenerate them with the extension installed:

```bash
python tools/docs_figures.py          # rewrite docs/assets/figures/
python tools/docs_figures.py --check  # verify they still match
```

`tests/integration/test_docs_figures.py` runs the same check.

Build the site with `mkdocs build --strict`, or preview it with `mkdocs serve`,
after installing `mkdocs-material==9.7.7`. The visual rules are in `DESIGN.md`.

`tools/mkdocs_hooks.py` runs during the build. It writes each figure's numbers
into the page as tables, renders the `faq` list in a page's front matter with its
structured data, and creates `llms.txt` and `llms-full.txt`. Give a new page a
`title`, a `description` and a first paragraph that answers what the page is
about.

## Packaging

Build the Python wheel with `maturin build --release`. The Python binding crate
is not published as a Rust library; `sedmetrics-core` is the intended Rust
distribution.
