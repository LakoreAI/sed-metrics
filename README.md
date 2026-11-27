# SEDMetrics

Evaluation metrics for Sound Event Detection (SED), with a Rust computational
core and Python bindings through PyO3. SEDMetrics evaluates model outputs; it
does not train models, extract audio features or detect sound events itself.

The project has two goals: faithful, efficient implementations of established
evaluation protocols, and research on what conventional offline metrics cannot
measure — in particular the difference between estimated event boundaries and
the time at which a decision actually becomes available.

## Status

This is an early bootstrap. Only the metric below is implemented; everything
else in the roadmap is planned.

| Area | Status |
| --- | --- |
| Collar-based event precision / recall / F1 (micro, macro, per class, with counts and mean localization error) | Implemented — Rust core + Python bindings |
| Segment-based precision / recall / F1 with S/D/I error rate | Implemented — Rust core + Python bindings |
| PSDS (intersection-based DTC/GTC/CTTC, PSDS1/PSDS2 profiles) | Implemented — Rust core + Python bindings |
| Dataset adapters: URBAN-SED v2.0.0 (dir or `.tar.gz`), AudioSet strong parquet | Implemented — `pyarrow` optional, AudioSet only |
| Parity with `sed_eval` 0.2.1 (event, segment) and `sed_scores_eval` 0.0.4 (PSDS) | Passing, including per-class PSDS curves |
| JSON evaluation report + `sedmetrics evaluate` CLI | Implemented |
| Frame metrics on an arbitrary score grid, piPSDS / post-processing-independent evaluation | Not implemented |
| Streaming / online metrics (deadline recall, AUDR, false alerts per hour) | Not implemented, protocol provisional |
| Diagnostics, post-processing, soft-label metrics | Not implemented |
| CLI | Not implemented |

Correctness caveats that apply right now:

- Event and segment parity is verified against `sed_eval` 0.2.1; PSDS parity
  against `sed_scores_eval` 0.0.4. There is no parity evidence for `psds_eval`
  (superseded here by the intersection-based criteria) or scikit-learn.
- Parity runs use synthetic predictions derived from references, on sampled
  URBAN-SED test clips and AudioSet strong clips. They are not a benchmark of
  any system.
- `sedmetrics evaluate` reads predictions from a TSV/CSV table and reports
  event/segment metrics; PSDS needs score tracks and is available through the
  Python API only. DCASE score files and model checkpoints are not read, and
  there is no batch/streaming API.
- No license has been chosen yet; do not redistribute until the maintainer
  settles it.

## Install (from source)

Requires Rust 1.85+ and Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release
pip install "sedmetrics[data]"    # optional: pyarrow, for AudioSet parquet
```

## Usage

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
result = dataset.psds(
    {"soundscape_test_1": (boundaries, {"siren": frame_scores})},
    dtc_threshold=0.7, gtc_threshold=0.7, alpha_st=1.0,
)
print(result.psds, result.classes[0].tpr)
```

DCASE PSDS1 is the default configuration; PSDS2 means
`dtc_threshold=0.1, gtc_threshold=0.1, cttc_threshold=0.3, alpha_ct=0.5`.
`alpha_st` defaults to 1.0 here, unlike `sed_scores_eval` (0.0).

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

The PSDS parity suite needs `sed_scores_eval`, which needs a working SciPy and
`pandas < 3`. On this machine the Python 3.10 SciPy wheel does not load, so the
oracle runs from a separate 3.12 environment:

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

- `docs/metrics/event_f1.md` — specification of the implemented metric
  (definition, matching policy, aggregation, undefined values, defaults,
  hand-computed example, parity evidence, limitations).
- `docs/metrics/segment_f1.md` — segment-based metric and S/D/I decomposition.
- `docs/metrics/psds.md` — PSDS definition, criteria, profiles and parity.
- `docs/adapters.md` — dataset formats, id assignment, duration rules.

## License

Not yet decided. The license must be chosen by the maintainer before any
release or redistribution.
