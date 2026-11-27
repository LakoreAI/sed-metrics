---
description: Install SEDMetrics and evaluate sound event predictions from Python or Rust.
---

# Getting started with SEDMetrics

SEDMetrics requires Python 3.10 or newer. Building from source requires Rust
1.85 or newer and maturin. A Rust compiler is not needed when a compatible
wheel is available.

## Install with pip

```bash
python -m pip install sedmetrics
```

If a compatible wheel is unavailable, pip builds the source distribution and
needs a Rust compiler.

## Install from source

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install maturin
maturin develop --release
```

For AudioSet Strong parquet adapters, install the optional dependency with
`python -m pip install '.[data]'` from the repository root.

## Evaluate more than one metric

```python
from sedmetrics import SEDMetrics

results = SEDMetrics.eval(
    references=[(0, 0, 0.0, 1.0)],
    predictions=[(0, 0, 0.05, 1.0)],
    recordings={0: 2.0},
    metrics=["event_f1", "segment_f1"],
)
print(results["event_f1"].f1)
print(results["segment_f1"].error_rate)
```

The `metrics` argument returns a dictionary even when it has one entry.
The singular `metric` argument returns one result. Supply metric-specific
settings through `metric_options`, keyed by metric name.

## Rust

Add the Rust crate to `Cargo.toml`:

```toml
[dependencies]
sedmetrics-core = "0.1.0"
```

The crate exposes typed events, configurations, results, and validation errors.
See the [API reference](api.md) for the supported calls.
