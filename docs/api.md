---
title: "SEDMetrics Python and Rust API"
description: "Reference for SEDMetrics.eval, the lower-level Python functions and the sedmetrics-core Rust crate for sound event evaluation."
---

# SEDMetrics API reference

## Python entry point

`SEDMetrics.eval(references, predictions=None, *, mode=None, metric=None,
metrics=None, recordings=None, scores=None, alerts=None, metric_options=None,
**options)` selects an evaluator.

| Selection | Required input | Result |
| --- | --- | --- |
| Default or `metric="event_f1"` | Reference and predicted events | Event F1 result |
| `metric="segment_f1"` | Events and recording durations | Segment result |
| `metric="psds"` | Events, durations, score tracks | PSDS result |
| `metric="pipsds"` | Events, durations, named processed score tracks | piPSDS envelope |
| `mode="frame"` | Aligned labels and scores, or events, durations and score tracks | Frame statistics |
| `mode="probability"` | Aligned targets and probabilities | Brier result |
| `mode="streaming"` | Events, durations, class IDs, and CREATE alerts | Experimental streaming statistics |

The first two arguments change meaning with the mode. In probability mode,
`references` holds the targets and `scores=` the probabilities. In aligned frame
mode, `references` holds Boolean labels and `scores=` the frame scores.
Streaming mode takes the alerts through `alerts=`.

For event metrics, `metrics=[...]` returns a dictionary of results and
`metric_options` maps metric names to option dictionaries. In aligned frame mode,
`metrics` selects scalar fields while retaining counts and configuration.
Event-based frame mode returns all its classwise and aggregate metrics.

## Lower-level Python functions

- `sedmetrics.event.f1` evaluates collar-based event F1.
- `sedmetrics.segment.f1` evaluates segment F1 and error rate.
- `sedmetrics.frame.evaluate` evaluates aligned binary labels and scores.
- `sedmetrics.frame.events` maps events to score intervals and evaluates classes.
- `sedmetrics.frame.brier` evaluates aligned probabilities and soft targets.
- `sedmetrics.psds.psds` and `sedmetrics.psds.pipsds` evaluate score tracks.
- `sedmetrics.experimental.streaming.evaluate` evaluates CREATE alert logs.
- `sedmetrics.report.evaluate` constructs a JSON-compatible report of event and
  segment metrics, plus PSDS when `scores=` is supplied.

See each [metric specification](choosing-metrics.md) for parameters, tie
handling, aggregation, and undefined values. Results are structured objects or
dictionaries; undefined values are `None`.

## Rust crate

The `sedmetrics-core` crate exports domain types such as `Event`, `Recording`,
`ScoreTrack`, and `CreateAlert`, together with typed metric functions including
`event_f1`, `segment_metrics`, `frame_metrics`, `psds`, `brier`, and
`evaluate_streaming`. The crate does not perform file I/O or depend on Python.
