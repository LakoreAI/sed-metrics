---
description: Collar-based sound event detection precision, recall, F1, matching and aggregation.
---

# Collar-based event precision, recall and F1

Specification identifier: `event_f1/1`.

Status: **implemented** (bootstrap). Established metric family; selected
fixtures are compared against `sed_eval` 0.2.1 as described below.

Source: Mesaros, Heittola and Virtanen, *Metrics for Polyphonic Sound Event
Detection*, Applied Sciences 6(6):162, 2016, <https://doi.org/10.3390/app6060162>,
together with the event-based evaluation in `sed_eval` 0.2.x. The collar rules
below follow that protocol; deviations are listed under *Limitations*.

## 1. Input representation

Each event is `(recording_id, class_id, onset, offset)`:

- `recording_id`, `class_id`: nonnegative integer identifiers. Names are mapped
  to identifiers by adapters, not by this metric.
- `onset`, `offset`: seconds, `f64`.
- Intervals are half-open, `[onset, offset)`, and must have positive length.

Validation is strict and always on: non-finite timestamps, negative onsets,
`offset <= onset` and (when recording durations are supplied) events extending
past the recording end or referencing an unknown recording raise an error. Rows
are never dropped silently.

Optional recording durations (`{recording_id: duration_seconds}`) are used only
for boundary validation in this metric; they are required by exposure-based
metrics such as false alerts per hour, not by event F1.

## 2. Definition

For one `(recording, class)` group, a prediction `p` is **eligible** for a
reference `r` when

```
|p.onset  - r.onset|  <= onset_collar
|p.offset - r.offset|  <= max(offset_collar, offset_ratio * (r.offset - r.onset))
```

with the second condition applied only when `evaluate_offset` is true.

Counts over all classes and recordings:

```
TP = number of matched reference/prediction pairs
FP = n_predicted - TP        (insertions)
FN = n_reference - TP        (deletions)

precision = TP / (TP + FP) = TP / n_predicted
recall    = TP / (TP + FN) = TP / n_reference
F1        = 2 TP / (2 TP + FP + FN)
```

`mean_onset_error` and `mean_offset_error` are the mean absolute differences
over matched pairs only, in seconds.

## 3. Matching policy

- Matching is one-to-one: a reference pairs with at most one prediction and a
  prediction with at most one reference.
- Eligibility is evaluated independently per `(recording, class)` group; a
  prediction can never match a reference of another class or recording.
- Matching is **maximum cardinality** within each group, computed with
  augmenting paths (Kuhn's algorithm). A greedy assignment is not used, because
  it can lose valid true positives (a regression test covers this).
- Among maximum-cardinality matchings the implementation does **not** minimise
  total localization error. The selected matching is deterministic for a given
  input order: events are sorted by `(onset, offset)` and references are
  processed in that order, preferring the lowest-index eligible prediction.
  Counts are invariant to input permutation; the particular pairs need not be.
- Collar comparisons are exact (`<=`) with **no** floating-point epsilon.
  `offset <= onset + collar` matches; `offset` one ULP beyond does not. Note
  that decimal inputs such as `1.2 - 1.0` are not exact in binary, so
  "0.2 s collar" is not bit-exactly 0.2 in every case. Timings that matter at
  the boundary should be expressed in binary-exact values or compared through
  fixtures that acknowledge this.
- Ties between predictions (identical onset and offset) are resolved by input
  order; they are interchangeable for the counts and for the error statistics.

## 4. Aggregation, units and undefined values

`average="micro"` pools counts over all classes and then computes the ratios
(the `TP`-weighted result). `average="macro"` computes each ratio per class and
takes the unweighted mean over the classes where **that** ratio is defined.

Consequences, which are deliberate:

- Macro F1 is *not* the harmonic mean of macro precision and macro recall, and
  the precision, recall and F1 means can have different support (a class with
  predictions but no references contributes to macro precision only).
- Per-class statistics are always returned, sorted by class id, including
  classes that appear only in references or only in predictions. Nothing is
  dropped: `result.classes` and `result.n_classes` make the support auditable.

Undefined results are `None` (JSON `null`), never `NaN` and never silently zero:

| Situation | precision | recall | F1 |
| --- | --- | --- | --- |
| No predictions | `None` | value | value |
| No references | value | `None` | value |
| No predictions and no references | `None` | `None` | `None` |

Units: ratios are dimensionless; localization errors are seconds.

## 5. Defaults and profiles

The defaults form the `dcase2016` profile: `onset_collar = 0.2`,
`offset_collar = 0.2`, `offset_ratio = 0.2`, `evaluate_offset = True`, and
`average = "micro"`.

Provenance: the collar values and the `max(offset_collar, ratio * duration)`
offset rule follow the 2016 Mesaros et al. protocol and DCASE 2016 Task 2
practice. Micro averaging is the `sed_eval`-style overall result (pooled
counts). Neither value is universal: other challenges use different collars and
macro averaging, so callers should pass the profile they intend to reproduce.

`sed_eval` 0.2.1 exposes the same rule as `t_collar` plus
`percentage_of_length`, but its `percentage_of_length` default is **0.5**, not
0.2. Reproducing this profile in `sed_eval` requires passing
`t_collar=0.2, percentage_of_length=0.2` explicitly.

`evaluate_offset=False` implements an onset-only protocol and must be labelled
as such in reports.

## 6. Hand-computed example

References `[(0,0,0.0,1.0), (0,0,2.0,3.0), (0,0,4.0,5.0)]`, predictions
`[(0,0,0.0,1.0), (0,0,2.0,3.0), (0,0,7.0,8.0)]`, collars `0.2 / 0.2 / 0.2`:

- `TP = 2`, `FP = 1`, `FN = 1`
- `precision = recall = 2/3`, `F1 = 4/6 = 2/3`
- mean onset and offset error over the two matched pairs: `0` s

Macro is not the F1 of macro precision and recall. With class 0 holding 1 match
among 10 references and class 1 holding 1 match among 10 predictions, each
class has `F1 = 2/11`, so macro `F1 = 2/11 ≈ 0.182`, while macro precision and
macro recall are both `0.55` and their harmonic mean is `0.55`.

## 7. Related implementations, verification and complexity

- References: `sed_eval` 0.2.1 event-based metrics with
  `event_matching_type="optimal"` (Hopcroft–Karp maximum-cardinality matching),
  Mesaros et al. 2016.
- Parity: `tests/parity/test_event_f1_sed_eval.py` compares counts and
  P/R/F1 against `sed_eval` with the same `t_collar` and
  `percentage_of_length`. Cases: hand fixtures, exact collar boundaries, an
  onset-only protocol, seeded random perturbations, 120 URBAN-SED test clips
  (638 events, 10 classes) and 60 AudioSet strong clips (625 events, 86
  classes). Counts agree exactly; ratios agree to `1e-12`. The parity
  dependency is a test-only extra, never a runtime dependency.
- One intentional reporting difference: `sed_eval` counts leftover
  reference/system pairs that satisfy the collars but disagree on class as
  **substitutions** (`Nsubs`) and subtracts them from its `Nfp`/`Nfn`. This
  implementation follows the classification convention
  `FP = n_predicted - TP`, `FN = n_reference - TP`, so its insertion and
  deletion counts equal `sed_eval`'s `Nfp + Nsubs` and `Nfn + Nsubs`.
  Substitution counts are not reported yet.
- Empty-system behaviour also differs by design: with no predictions,
  `sed_eval` reports `NaN` F1 and precision; this implementation reports
  precision `None` and `F1 = 0` (see §4).
- Additional local evidence: hand-computed fixtures and a brute-force
  maximum-matching oracle over deterministic pseudo-random small cases.
- Numerical tolerance: fixtures compare with `1e-12` absolute tolerance on
  ratios derived from exact integer counts.
- Complexity: eligibility is `O(n_ref * n_pred)` per group and Kuhn's algorithm
  is `O(V * E)` in the worst case; both are computed per
  `(recording, class)` group, so independent recordings and classes scale
  separately.

## Limitations

- Maximum-cardinality matching does not minimise localization error, and no
  per-class onset/offset-constrained matching is offered.
- No substitution (`Nsubs`) statistic and no error rate; insertion/deletion
  counts follow the FP/FN convention described in §7, which differs from
  `sed_eval`'s event-based reporting.
- Only one matching policy is implemented; intersection-based metrics (PSDS)
  will need a different one and must not reuse this matcher.
- No evaluation of `evaluate_offset=False` against a reference implementation.
- No support yet for confidence values, class names, score tracks or recording
  boundaries beyond optional validation.
- Collar parameters are in seconds only; there is no sample-index or tick
  representation.
