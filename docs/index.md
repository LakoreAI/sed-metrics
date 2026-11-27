---
title: "Sound event detection metrics"
description: "SEDMetrics scores sound event detection with event F1, segment, frame, PSDS, piPSDS, Brier and streaming metrics in Python and Rust."
template: landing.html
faq:
  - q: "Does SEDMetrics train or run a model?"
    a: "No. It scores outputs you already have: events, score tracks, probabilities or alert logs."
  - q: "Which reference implementations is it tested against?"
    a: "Selected fixtures match sed_eval 0.2.1, sed_scores_eval 0.0.4 and scikit-learn. There is no parity evidence for psds_eval."
  - q: "Are the streaming metrics stable?"
    a: "No. They are experimental, accept CREATE alerts only and have not been validated on real detector traces."
  - q: "What happens to undefined values?"
    a: "An undefined ratio is returned as None, never as NaN or a silent zero."
  - q: "Which platforms are tested?"
    a: "macOS arm64 and Linux x86_64 are the first tier. CI also runs a Windows job. Python 3.10 to 3.13 are supported."
---

# SEDMetrics: sound event detection evaluation

SEDMetrics evaluates temporal, polyphonic sound event detection outputs with a
Rust core and Python bindings: event, segment, frame, PSDS, piPSDS, Brier and
experimental streaming metrics. See [getting started](getting-started.md) and
[how metrics penalise mistakes](penalties.md).
