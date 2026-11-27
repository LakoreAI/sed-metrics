---
description: Evaluate sound event detection predictions and scores with Python and Rust.
---

# SEDMetrics: sound event detection evaluation

SEDMetrics evaluates temporal, polyphonic sound event detection (SED) outputs.
It provides a Rust core and Python bindings for event, segment, frame, and
score-based metrics. An experimental alert-log protocol measures when a
detector made a decision available.

[Get started](getting-started.md){ .md-button .md-button--primary }
[Choose a metric](choosing-metrics.md){ .md-button }

## Metrics at a glance

| Input | Metrics | Use |
| --- | --- | --- |
| Events | Collar F1; segment F1 and error rate | Compare event boundaries or activity in fixed segments |
| Score tracks | Frame F1, AP, AUROC; PSDS and piPSDS | Evaluate frame decisions or threshold-based operating curves |
| Probabilities | Brier score | Compare probabilities with aligned binary or soft targets |
| CREATE alerts | Deadline recall, AUDR, false alerts per hour | Study decision availability under the experimental protocol |

## Evaluate event predictions

```python
from sedmetrics import SEDMetrics

result = SEDMetrics.eval(
    references=[(0, 0, 0.0, 1.0)],
    predictions=[(0, 0, 0.05, 1.0)],
)
print(result.f1, result.n_correct)
```

Events are `(recording_id, class_id, onset, offset)`. Times are seconds and
intervals are half-open. See [event F1](metrics/event_f1.md) for collars,
matching, and undefined values.

## What the results can tell you

Offline metrics use final predictions or scores. They do not record when a
decision was emitted. The [streaming protocol](streaming-protocol.md) needs an
alert log with explicit emission and audio availability times. Its metrics are
experimental and have not been independently validated on real alert traces.
