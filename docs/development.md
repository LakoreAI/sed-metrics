# Development and validation

Install Rust 1.85 or newer and Python 3.10 or newer. Create a virtual
environment, install maturin and the test dependencies, then build the extension:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install maturin '.[test]'
maturin develop --release
```

Run the core and Python checks:

```bash
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test -p sedmetrics-core
python -m pytest
```

Install `.[parity]` to run selected comparisons against pinned `sed_eval`,
`sed_scores_eval`, and scikit-learn versions. Dataset-dependent cases need
`SEDMETRICS_RAW_DATA` and skip when their files are unavailable. The comparison
fixtures do not establish parity for every possible input.

Build the documentation with `mkdocs build --strict` after installing
`mkdocs-material`. Build the Python wheel with `maturin build --release`. The
Python binding crate is not published as a Rust library; `sedmetrics-core` is
the intended Rust distribution.
