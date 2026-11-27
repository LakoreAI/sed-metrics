---
title: "Install and use SEDMetrics"
description: "Install SEDMetrics with pip or from source, then score sound event predictions from Python or add the core crate to a Rust project."
faq:
  - q: "Which Python versions does SEDMetrics support?"
    a: "CPython 3.10 to 3.13, with one wheel per platform."
  - q: "Do I need a Rust compiler?"
    a: "Only to build from source. A compatible wheel installs without one. Building needs Rust 1.85 or newer."
---

# Getting started with SEDMetrics

SEDMetrics is a Python and Rust library that scores sound event detection output. Install it, pass reference and predicted events to `SEDMetrics.eval`, and read the metric together with the counts behind it.

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
