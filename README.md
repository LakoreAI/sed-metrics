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
| Frame metrics, segment metrics, PSDS / intersection metrics, threshold sweeps | Not implemented |
| Streaming / online metrics (deadline recall, AUDR, false alerts per hour) | Not implemented, protocol provisional |
| Diagnostics, post-processing, soft-label metrics | Not implemented |
| CLI | Not implemented |

Correctness caveats that apply right now:

- Parity against `sed_eval`, `psds_eval`, `sed_scores_eval` and scikit-learn has
  **not** been run. The event F1 implementation is currently validated by
  hand-computed fixtures, edge-case tests and a brute-force matching oracle.
- The Python API is a single function; there is no batch API, no
  `Evaluator` class, no adapter for DCASE TSV files and no CLI.
- No license has been chosen yet; do not redistribute until the maintainer
  settles it.

## Install (from source)

Requires Rust 1.85+ and Python 3.10+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release
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

## Development

```bash
cargo fmt --all -- --check
cargo clippy -p sedmetrics-core --all-targets -- -D warnings
cargo test -p sedmetrics-core          # pure Rust, no Python needed
maturin develop --release
python -m pytest                       # Python integration tests
```

`sedmetrics-python` is built with the `pyo3/extension-module` feature by
maturin, so Rust-level checks target `sedmetrics-core`; the binding itself is
covered by the Python tests.

## Documentation

- `docs/metrics/event_f1.md` — specification of the implemented metric
  (definition, matching policy, aggregation, undefined values, defaults,
  hand-computed example, limitations).

## License

Not yet decided. The license must be chosen by the maintainer before any
release or redistribution.
