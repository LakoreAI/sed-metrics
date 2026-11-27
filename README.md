# SEDMetrics

SEDMetrics is a Python and Rust library for evaluating sound event detection
(SED): systems that report which sounds occur in a recording and when. You give
it the annotated events and a detector's output, and it returns standard scores
together with the counts behind them.

It is for people who train, compare or ship such detectors and need numbers they
can explain. The metrics run in a Rust core with no third-party dependencies, and
the Python package installs without runtime dependencies of its own.

Documentation: <https://lakoreai.github.io/sed-metrics/>

## Why the choice of metric matters

The same mistake can cost everything under one metric and nothing under another.
These are four detector outputs scored against the same three events:

| What the detector did | Event F1 | Segment F1 | PSDS1 | PSDS2 |
| --- | --- | --- | --- | --- |
| Reported every onset 0.4 s late | 0.00 | 1.00 | 1.00 | 1.00 |
| Split one event in two | 0.57 | 1.00 | 1.00 | 1.00 |
| Missed one event | 0.80 | 0.86 | 0.50 | 0.50 |
| Gave one event the wrong class | 0.67 | 0.50 | 0.00 | 0.00 |

SEDMetrics puts these metrics behind one interface, so you can score one output
under several of them and see what each charges for.
[How metrics penalise mistakes](https://lakoreai.github.io/sed-metrics/penalties/)
has the full comparison and its setup.

The project also studies what offline scores cannot show: when a detector's
decision actually became available.

## Quick start

```bash
python -m pip install sedmetrics
```

An event is `(recording_id, class_id, onset, offset)`, with times in seconds:

```python
from sedmetrics import SEDMetrics

references = [(0, 0, 2.0, 4.0), (0, 0, 5.0, 7.0), (0, 1, 10.0, 14.0)]
# A detector that reports every onset 0.4 s late.
predictions = [(r, c, onset + 0.4, offset) for r, c, onset, offset in references]

results = SEDMetrics.eval(
    references, predictions, recordings={0: 20.0}, metrics=["event_f1", "segment_f1"]
)

event = results["event_f1"]
print(event.f1, event.n_insertions, event.n_deletions)  # 0.0 3 3
print(results["segment_f1"].f1)                         # 1.0
```

Event F1 allows 0.2 s on an onset, so all three detections count as false alarms
and all three events as missed. In 1 s segments the same output is perfect.

## What you can evaluate

| You have | You can compute | Read |
| --- | --- | --- |
| Reference and predicted events | Collar-based event F1 | [Event F1](https://lakoreai.github.io/sed-metrics/metrics/event_f1/) |
| Reference and predicted events | Segment F1 and substitution, deletion and insertion error rate | [Segment metrics](https://lakoreai.github.io/sed-metrics/metrics/segment_f1/) |
| Frame scores | Precision, recall, F1, average precision, AUROC | [Frame metrics](https://lakoreai.github.io/sed-metrics/metrics/frame_events/) |
| Score tracks | PSDS1, PSDS2 and custom profiles | [PSDS](https://lakoreai.github.io/sed-metrics/metrics/psds/) |
| Several processed score tracks | piPSDS | [piPSDS](https://lakoreai.github.io/sed-metrics/metrics/pipsds/) |
| Probabilities | Brier score, with binary or soft targets | [Brier score](https://lakoreai.github.io/sed-metrics/metrics/brier/) |
| Timestamped alert logs | Deadline recall, AUDR, false alerts per hour (experimental) | [Streaming protocol](https://lakoreai.github.io/sed-metrics/streaming-protocol/) |

Loaders for URBAN-SED v2.0.0 and AudioSet Strong, a JSON report and a
`sedmetrics evaluate` command are described in
[dataset adapters](https://lakoreai.github.io/sed-metrics/adapters/). AudioSet
parquet needs the optional extra: `pip install "sedmetrics[data]"`.

## How far to trust the numbers

- Input is checked strictly. Malformed events raise an error, and an undefined
  ratio is returned as `None`, never as `NaN` or a silent zero.
- Selected fixtures are compared with `sed_eval` 0.2.1 (event and segment),
  `sed_scores_eval` 0.0.4 (PSDS and piPSDS) and scikit-learn (frame and Brier).
  There is no parity evidence for `psds_eval`, and the fixtures do not cover
  every possible input.
- Each metric has a written specification. Where the code currently differs from
  it, the page says so.
- The streaming metrics are experimental and have not been validated on real
  detector traces.

SEDMetrics scores outputs only. It does not train models, extract audio features
or detect sounds, and it has no diagnostics or post-processing tools yet.

## Rust

```toml
[dependencies]
sedmetrics-core = "0.1.0"
```

The crate has typed events, configurations, results and validation errors. It
does no file input or output and does not depend on Python.

## Install from source

You need Rust 1.85 or newer and Python 3.10 or newer.

```bash
python -m venv .venv && source .venv/bin/activate
pip install maturin
maturin develop --release
```

A source distribution from PyPI also needs a Rust compiler.

## Supported platforms

| Tier | Platforms | Status |
| --- | --- | --- |
| 1 | macOS arm64, Linux x86_64 | Built and tested |
| 2 | Windows x86_64 | Built and tested by a CI job |
| 2 | Linux aarch64 | Expected to build, untested |
| none | 32-bit targets, musl wheels | Not supported |

One wheel per platform covers CPython 3.10 to 3.13 through the `abi3-py310`
stable ABI.

## Contributing

[Development and validation](https://lakoreai.github.io/sed-metrics/development/)
covers the checks, the parity suite and the documentation build. The visual rules
for the site are in [DESIGN.md](https://github.com/LakoreAI/sed-metrics/blob/main/DESIGN.md).

## License

Licensed under the Apache License, Version 2.0
([LICENSE-APACHE](https://github.com/LakoreAI/sed-metrics/blob/main/LICENSE-APACHE)).
Unless you explicitly state otherwise, any contribution intentionally submitted
for inclusion in this project shall be licensed under the same terms, without
additional conditions.

The reference tools used in tests (`sed_eval`, `sed_scores_eval`, scikit-learn)
are development dependencies and are not distributed with this project.
