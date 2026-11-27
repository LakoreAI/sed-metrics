# SEDMetrics

Evaluation metrics for Sound Event Detection (SED), with a Rust computational
core and Python bindings through PyO3. SEDMetrics evaluates model outputs; it
does not train models, extract audio features or detect sound events itself.

The project has two goals: faithful, efficient implementations of established
evaluation protocols, and research on what conventional offline metrics cannot
measure, in particular the difference between estimated event boundaries and
the time at which a decision actually becomes available.

## Status

This is an early bootstrap. The implemented and planned features are listed below.

| Area | Status |
| --- | --- |
| Collar-based event precision / recall / F1 (micro, macro, per class, with counts and mean localization error) | Implemented in Rust and Python |
| Segment-based precision / recall / F1 with S/D/I error rate | Implemented in Rust and Python |
| PSDS (intersection-based DTC/GTC/CTTC, PSDS1/PSDS2 profiles) | Implemented in Rust and Python |
| Dataset adapters: URBAN-SED v2.0.0 (dir or `.tar.gz`), AudioSet strong parquet | Implemented; `pyarrow` is optional and only needed for AudioSet |
| Reference parity | Tested for selected fixtures against `sed_eval` 0.2.1 (event, segment) and `sed_scores_eval` 0.0.4 (PSDS), including per-class PSDS curves |
| JSON evaluation report + `sedmetrics evaluate` CLI | Implemented |
| Frame precision/recall/F1, AP and AUROC | Implemented for aligned labels or event-to-frame mapping, with classwise, micro and macro results for event tracks |
| piPSDS | Implemented for explicitly supplied post-processed score tracks; reference parity tested on a fixture |
| Streaming / online metrics | Experimental CREATE-only fixed assignment, deadline recall, AUDR and false alerts per hour |
| Soft-label Brier score | Implemented for aligned single-class targets and probabilities |
| Diagnostics and post-processing | Not implemented |

Correctness caveats that apply right now:

- Selected event and segment fixtures are compared with `sed_eval` 0.2.1,
  PSDS and piPSDS fixtures with `sed_scores_eval` 0.0.4, and frame and Brier
  fixtures with scikit-learn. There is no parity evidence for `psds_eval`.
- Parity runs use synthetic predictions derived from references, on sampled
  URBAN-SED test clips and AudioSet strong clips. They are not a benchmark of
  any system.
- `sedmetrics evaluate` reads predictions from a TSV/CSV table and reports
  event/segment metrics; PSDS needs score tracks and is available through the
  Python API only. DCASE score files and model checkpoints are not read. The
  experimental streaming API evaluates complete CREATE alert logs.

## Install

```bash
python -m pip install sedmetrics
```

If a compatible wheel is unavailable, installing the source distribution
requires a Rust compiler. The Rust library is available as `sedmetrics-core`.

## Install from source

Requires Rust 1.85+ and Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release
pip install "sedmetrics[data]"    # optional: pyarrow, for AudioSet parquet
```

## Usage

For a single metric, use the simple entry point:

```python
from sedmetrics import SEDMetrics

result = SEDMetrics.eval(
    references=[(0, 0, 0.0, 1.0)],
    predictions=[(0, 0, 0.05, 1.0)],
)
print(result.f1, result.n_correct)
```

The default is collar-based event F1. Pass `metric="segment_f1"` and
`recordings={0: 2.0}` for segment metrics, or `metric="psds"`, `scores=...`
and `recordings=...` for PSDS. Metric-specific options can be passed as keyword
arguments. A `Dataset` can be passed as `references` to use names and its
recording durations. The lower-level APIs remain available:

```python
results = SEDMetrics.eval(
    references=[(0, 0, 0.0, 1.0)],
    predictions=[(0, 0, 0.05, 1.0)],
    recordings={0: 2.0},
    metrics=["event_f1", "segment_f1"],
    metric_options={"event_f1": {"onset_collar": 0.1}},
)
print(results["event_f1"].f1, results["segment_f1"].f1)
```

`metrics` always returns a dictionary, even with one selection. The singular
`metric` argument returns a single result. When combining event metrics with
PSDS, supply both `predictions` and complete `scores`.

```python
import sedmetrics as sm

result = sm.event.f1(
    references=[(0, 0, 0.0, 1.0), (0, 0, 2.0, 3.0), (0, 0, 4.0, 5.0)],
    predictions=[(0, 0, 0.0, 1.0), (0, 0, 2.0, 3.0), (0, 0, 7.0, 8.0)],
    onset_collar=0.2,
    offset_collar=0.2,
    offset_ratio=0.2,
    average="micro",
)

print(result.f1, result.precision, result.recall)
print(result.n_correct, result.n_insertions, result.n_deletions)
print(result.to_dict())
```

Each event is `(recording_id, class_id, onset, offset)` in seconds, a mapping
with those keys, or an object exposing them as attributes. Intervals are
half-open, `[onset, offset)`. Undefined ratios are `None`, never `NaN`.

Evaluating on a dataset, using class and recording names instead of ids:

```python
dataset = sm.adapters.load_urban_sed("data/raw/URBAN-SED_v2.0.0.tar.gz", split="test")

result = dataset.event_f1(
    [("soundscape_test_1", "siren", 1.05, 2.45)],
    average="macro",
)
```

See `docs/adapters.md` for dataset layouts, id assignment and duration rules.

Segment-based metrics and a reproducible JSON report:

```python
dataset = sm.adapters.load_urban_sed("data/raw/URBAN-SED_v2.0.0.tar.gz", split="test")

print(dataset.segment_f1(predictions, segment_length=1.0).error_rate)

report = sm.report.evaluate(dataset, predictions, metrics=["event_f1", "segment_f1"])
sm.report.write_report(report, "results/run.json")

# or from the command line, with predictions in a TSV/CSV table
# sedmetrics evaluate --dataset urban-sed --root data/raw --predictions preds.tsv --out results/run.json
```

PSDS from per-frame scores:

```python
result = SEDMetrics.eval(
    references=[(0, 0, 1.0, 2.0)],
    metric="psds",
    recordings={0: 3.0},
    scores={0: ([0.0, 1.0, 2.0, 3.0], {0: [0.1, 0.9, 0.1]})},
)
print(result.psds, result.classes[0].tpr)
```

Supply a complete track for every recording and every evaluated class; its
boundaries must span the recording's full duration.

DCASE PSDS1 is the default configuration; PSDS2 means
`dtc_threshold=0.1, gtc_threshold=0.1, cttc_threshold=0.3, alpha_ct=0.5`.
`alpha_st` defaults to 1.0 here, unlike `sed_scores_eval` (0.0).

For explicitly aligned binary frame labels and scores, use:

```python
result = SEDMetrics.eval(
    references=[True, False, True], scores=[0.9, 0.8, 0.1],
    mode="frame", threshold=0.5,
    boundaries=[0.0, 0.2, 0.5, 1.0], weighting="duration",
)
print(result["f1"], result["average_precision"], result["auroc"])
```

The example uses pre-aligned labels for one class; see
`docs/metrics/frame_binary.md` for the contract.
Pass `metrics=["f1", "auroc"]` to select frame metrics; counts and configuration
are always included.

To map events to score frames and compute classwise, micro and macro metrics:

```python
result = SEDMetrics.eval(
    references=[(0, 0, 0.9, 1.0)], mode="frame", recordings={0: 2.0},
    scores={0: ([0.0, 1.0, 2.0], {0: [0.8, 0.2], 1: [0.1, 0.7]})},
    threshold=0.5,
)
print(result["micro"]["f1"], result["classes"][0]["f1"])
```

A frame is positive when it has any positive-duration overlap with a reference
of the same class; see `docs/metrics/frame_events.md` for the full contract.
For aligned soft targets and probabilities, use
`SEDMetrics.eval([0.2, 0.8], mode="probability", scores=[0.2, 0.5])` to
compute Brier score; its interpretation is in `docs/metrics/brier.md`.

For piPSDS, pass `metric="pipsds"` and a mapping from processing names to
complete score-track mappings via `scores`. The envelope can choose a different
processing at different operating points and is not a single deployed policy;
see `docs/metrics/pipsds.md`.

The experimental streaming baseline accepts immutable CREATE alerts with
explicit decision and audio availability times:

```python
result = SEDMetrics.eval(
    references=[(0, 0, 0.0, 0.5)], mode="streaming", recordings={0: 10.0},
    alerts=[(0, 1, 0, 0.1, 0.1, 0.1)],
    class_ids=[0], matching_window=1.0, deadlines=[0.25, 0.5], horizon=1.0, clock="simulated",
)
print(result["deadline_recall"], result["audr"], result["false_alerts_per_hour"])
```

The tuple is recording ID, alert ID, class ID, emitted time, audio available
until, and latest audio used (or `None`). The current protocol requires complete
recording observation, scores CREATE actions only, and treats references near
the end as censored. See `docs/streaming-protocol.md` for the matching policy,
clock assumptions, and limitations.

## Development

```bash
cargo fmt --all -- --check
cargo clippy -p sedmetrics-core --all-targets -- -D warnings
cargo test -p sedmetrics-core          # pure Rust, no Python needed
maturin develop --release
python -m pytest                       # unit, integration, parity

pip install "sedmetrics[parity]"       # sed_eval 0.2.1 oracle for parity tests
SEDMETRICS_RAW_DATA=/path/to/data/raw python -m pytest tests/parity
```

The PSDS parity suite needs `sed_scores_eval`, a working SciPy, and
`pandas < 3`. If the dependencies do not load in your development environment,
run the oracle from a separate Python 3.12 environment:

```bash
uv venv --python 3.12 .venv-oracle
uv pip install --python .venv-oracle/bin/python pytest pyarrow "sedmetrics[parity]" \
    --find-links dist
maturin build --release -o dist && uv pip install --python .venv-oracle/bin/python \
    --force-reinstall dist/*.whl
.venv-oracle/bin/python -m pytest tests/parity
```

`sedmetrics-python` is built with the `pyo3/extension-module` feature by
maturin, so Rust-level checks target `sedmetrics-core`; the binding itself is
covered by the Python tests.

## Documentation

- `docs/metrics/event_f1.md`: specification of the implemented metric
  (definition, matching policy, aggregation, undefined values, defaults,
  hand-computed example, parity evidence, limitations).
- `docs/metrics/segment_f1.md`: segment-based metric and S/D/I decomposition.
- `docs/metrics/psds.md`: PSDS definition, criteria, profiles and parity.
- `docs/adapters.md`: dataset formats, id assignment, duration rules.
- `docs/streaming-protocol.md`: experimental streaming evaluation contract and censoring policy.
- `docs/decisions/0001-baseline.md`: license, platforms, CI and metric order.

## Supported platforms

| Tier | Platforms | Status |
| --- | --- | --- |
| 1 | macOS arm64, Linux x86_64 | Built and tested |
| 2 | Linux aarch64, Windows x86_64 | Expected to build, untested |
| — | 32-bit targets, musl wheels | Not supported |

CPython 3.10-3.13 via the `abi3-py310` stable ABI, so one wheel per platform
works across those versions. Rust 1.85+ is required to build from source.

CI (`.github/workflows/ci.yml`) runs the Rust checks, the Python suite on Linux
and macOS, and the reference-parity suite on Linux. See GitHub Actions for the
status of the latest run.

## License

Licensed under the Apache License, Version 2.0 ([LICENSE-APACHE](LICENSE-APACHE)).
Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in this project shall be licensed under the same terms, without
additional conditions.

The reference oracles used in tests (`sed_eval`, `sed_scores_eval`) are
development-only dependencies and are not distributed with this project.
