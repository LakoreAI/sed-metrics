---
title: "ADR 0001: project baseline"
description: "Decision record for the SEDMetrics license, supported platforms, continuous integration and the order in which metrics were built."
---

# ADR 0001: project baseline (license, platforms, CI, metric order)

Status: historical baseline recorded 2026-11-27. The maintainer approved
Apache-2.0 for publication. The experimental streaming implementation and its
censoring policy are specified in `docs/streaming-protocol.md`.

## Context

The scope document left four decisions open: license and supported platforms,
the streaming matching protocol, the order of the remaining metrics, and
whether to add CI before the metric surface stabilises. This ADR records the
choices so that implementations, reports and releases do not re-litigate them.

## Decisions

### 1. License: Apache-2.0 only

Reversible by the maintainer, but applied here so the repository is usable.

- The canonical `LICENSE-APACHE` (sha256 `cfc7749b…523d30`) is at the
  repository root; `Cargo.toml` and `pyproject.toml` carry `Apache-2.0`.
- Rationale: an explicit patent grant, a single unambiguous license, and no
  per-user choice to explain in downstream distributions. No third-party code
  was copied, so no upstream license obligation constrains this choice.
- Copyright holder: "The SEDMetrics authors", because the legal entity behind
  the `LakoreAI` organisation versus the individual maintainer is not settled.
  Changing the holder later is a metadata-only change.
- `sed_eval` and `sed_scores_eval` stay test-only dependencies; they are never
  distributed in the wheel.

### 2. Supported platforms

- Tier 1 (built and tested): macOS arm64, Linux x86_64.
- Tier 2 (expected to build, untested): Linux aarch64, Windows x86_64.
- Not supported: 32-bit targets, musl wheels, PyPy.
- Python: 3.10-3.13 through `abi3-py310`; one wheel per platform.
- Rust: MSRV 1.85, pinned in the workspace (required by PyO3 0.30).

Consequence: CI runs Linux x86_64 and macOS arm64; Windows/aarch64 builds are
best effort and cannot be claimed as verified.

### 3. CI: yes, now

`.github/workflows/ci.yml` has three jobs: `rust` (fmt, clippy with `-D
warnings`, core tests), `python` (wheel build + full Python suite on Linux
3.10/3.12 and macOS arm64 3.12), and `parity` (Linux 3.12 with `sed_eval` and
`sed_scores_eval`, synthetic fixtures only because the reference data is not in the
repository).

See GitHub Actions for the current status of the workflow.

Update, 2026-11-27: the `python` job now also runs on a Windows runner. Windows
stays tier 2.

### 4. Metric order

1. Frame metrics on an explicit score grid (precision, recall, F1, AP, AUROC).
2. Threshold sweeps / exact operating points (Ebbers et al. 2022), which also
   give PSDS an exact-threshold path to compare with its sampled sweep.
3. Streaming metrics, against `docs/streaming-protocol.md`.
4. piPSDS and post-processing-independent evaluation.
5. Diagnostics (fragmentation, merging, duration/class strata) and soft-label /
   probability metrics.

Each step still needs its own specification document and a reference oracle
before implementation; the order is a dependency order, not a deadline.

### 5. Streaming protocol

The initial proposal has since been revised; the current contract is in
`docs/streaming-protocol.md`:

- immutable CREATE alerts only; Update/Cancel/Close are not accepted;
- eligibility window `[reference onset, reference onset + matching_window]`,
  never pre-onset, no clamping of negative delays;
- one-to-one assignment per (recording, class) with maximum cardinality, then
  minimum total delay, with deterministic traversal ties;
- right-censored references (window not fully observed) are excluded from the
  fully observed cohort and counted, not treated as misses;
- duplicates and unmatched CREATE alerts are false alerts;
- exposure for false alerts per hour covers every evaluated recording.

## Consequences

- Reports can state the license, the tested platforms and the metric order.
- Streaming remains experimental and its contract is versioned separately.
- Anything not covered here (default averaging policy, timestamp precision,
  release versioning) stays open in the scope document and is decided per
  metric with its specification.
