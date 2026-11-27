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

## Score each kind of output

A single metric returns one result object. Event F1 is the default:

```python
from sedmetrics import SEDMetrics

result = SEDMetrics.eval(
    references=[(0, 0, 0.0, 1.0)],
    predictions=[(0, 0, 0.05, 1.0)],
)
print(result.f1, result.n_correct)
```

Pass `metric="segment_f1"` and `recordings={0: 2.0}` for segment metrics.
Metric options are keyword arguments, or `metric_options` when you select
several with `metrics`. When combining event metrics with PSDS, supply both
`predictions` and complete `scores`. A `Dataset` can stand in for `references`,
which brings its names and recording durations.

Events are `(recording_id, class_id, onset, offset)` in seconds, a mapping with
those keys, or an object with those attributes. Intervals are half-open,
`[onset, offset)`.

### PSDS from score tracks

```python
result = SEDMetrics.eval(
    references=[(0, 0, 1.0, 2.0)],
    metric="psds",
    recordings={0: 3.0},
    scores={0: ([0.0, 1.0, 2.0, 3.0], {0: [0.1, 0.9, 0.1]})},
)
print(result.psds, result.classes[0].tpr)
```

Supply a complete track for every recording and every evaluated class, with
boundaries that span the full recording. The defaults compute PSDS1; see
[PSDS1 and PSDS2](metrics/psds.md#psds1-and-psds2) for PSDS2. For piPSDS, pass
`metric="pipsds"` and a mapping from processing names to complete score-track
mappings.

### Frames from aligned labels

```python
result = SEDMetrics.eval(
    references=[True, False, True], scores=[0.9, 0.8, 0.1],
    mode="frame", threshold=0.5,
    boundaries=[0.0, 0.2, 0.5, 1.0], weighting="duration",
)
print(result["f1"], result["average_precision"], result["auroc"])
```

Pass `metrics=["f1", "auroc"]` to select frame metrics. Counts and configuration
are always included.

### Frames from events

```python
result = SEDMetrics.eval(
    references=[(0, 0, 0.9, 1.0)], mode="frame", recordings={0: 2.0},
    scores={0: ([0.0, 1.0, 2.0], {0: [0.8, 0.2], 1: [0.1, 0.7]})},
    threshold=0.5,
)
print(result["micro"]["f1"], result["classes"][0]["f1"])
```

A frame is positive when it overlaps a reference of the same class; see
[frame events](metrics/frame_events.md).

### Probabilities

```python
result = SEDMetrics.eval([0.2, 0.8], mode="probability", scores=[0.2, 0.5])
print(result["brier"])
```

See [Brier score](metrics/brier.md) for the meaning of soft targets. Alert logs
use the [streaming protocol](streaming-protocol.md).

## Rust

Add the Rust crate to `Cargo.toml`:

```toml
[dependencies]
sedmetrics-core = "0.1.1"
```

The crate exposes typed events, configurations, results, and validation errors.
See the [API reference](api.md) for the supported calls.
