---
title: "Segment-based F1 and error rate for SED"
description: "Definition and formulas of segment-based precision, recall, F1 and the substitution, deletion and insertion error rate."
faq:
  - q: "What segment length should I use?"
    a: "The default is 1 s, as in sed_eval-style DCASE results. Other work uses 0.5 s or 0.1 s, so report the value."
  - q: "What is the segment error rate?"
    a: "Substitutions plus deletions plus insertions, divided by the number of active reference segments. It can exceed 1."
  - q: "Does segment F1 punish a split detection?"
    a: "Only when the hole leaves a segment without any part of the detection."
---

# Segment-based precision, recall, F1 and error rate

Segment-based metrics cut each recording into fixed segments, 1 s by default, and check class by class whether the reference and the prediction are active in each one. They report precision, recall, F1 and an error rate made of substitutions, deletions and insertions.

Specification identifier: `segment_f1/1`.

Status: implemented. Established metric family; parity with `sed_eval` 0.2.1
is tested.

Source: Mesaros, Heittola and Virtanen, *Metrics for Polyphonic Sound Event
Detection*, Applied Sciences 6(6):162, 2016,
<https://doi.org/10.3390/app6060162>, and the segment-based evaluation in
`sed_eval` 0.2.1.

## What do segment metrics penalise?

Time is cut into fixed segments and each segment is scored as active or silent.
An error smaller than the segment it falls in can cost nothing at all. A black
cell is a hit; a red cell is a false positive or a miss. In the formulas, red
terms are the errors.

<div class="pen" data-figure="segment_f1"></div>

| Mistake | Effect |
| --- | --- |
| Boundary shifted inside the same segment | None |
| Boundary shifted across a segment edge | One more FP (insertion) or FN (deletion) segment |
| Hole in a detection | None while each segment still holds some of the detection |
| Two events merged across a gap | Segments lying wholly in the gap become false positives |
| Wrong class in an active segment | One substitution in the error rate, but one FP and one FN in F1 |

## 1. Input representation

Events `(recording_id, class_id, onset, offset)` in seconds, half-open
`[onset, offset)`, positive length, identical to the event-based metric.
Optional recording durations `{recording_id: duration_seconds}` define the
evaluated window. Malformed events and events outside their recording are
rejected, never clipped silently.

## 2. Definition

A segment is $S_k = [kL,\,(k+1)L)$ for segment length $L$ (`segment_length`,
default 1 s). Segment $k$ is active for class $c$ in a reference or prediction
set when at least one event of class $c$ overlaps $S_k$. In indices the set of
active segments is

$$
A_c = \bigcup_{e \in E_c}
\Bigl\{ \Bigl\lfloor \tfrac{e_{\text{on}}}{L} \Bigr\rfloor, \dots,
\Bigl\lceil \tfrac{e_{\text{off}}}{L} \Bigr\rceil - 1 \Bigr\}
$$

so an event that only touches a boundary does not activate the neighbouring
segment.

!!! deviation "Current behaviour: inexact segment lengths"

    The division is done in binary floating point. When $L$ is not exact in
    binary, a boundary can land one segment early: `[0.3, 0.4)` with `L = 0.1`
    activates two segments, because `0.3 / 0.1` is `2.9999999999999996`.
    `L = 0.5`, `1.0` and `2.0` are exact.

For each segment with reference active-class count $n_{\text{ref}}(k)$, predicted
count $n_{\text{sys}}(k)$ and overlap $n_{\text{both}}(k)$:

$$
TP = \sum_k n_{\text{both}}, \qquad
FP = \sum_k \bigl(n_{\text{sys}} - n_{\text{both}}\bigr), \qquad
FN = \sum_k \bigl(n_{\text{ref}} - n_{\text{both}}\bigr)
$$

$$
\cost{S} = \sum_k \bigl(\min(n_{\text{ref}}, n_{\text{sys}}) - n_{\text{both}}\bigr)
$$

$$
\cost{D} = \sum_k \max(0,\; n_{\text{ref}} - n_{\text{sys}}), \qquad
\cost{I} = \sum_k \max(0,\; n_{\text{sys}} - n_{\text{ref}})
$$

The sums run over segments and then over recordings. Per class the same counts
are accumulated for that class only. The evaluated window of a recording is its
supplied duration, otherwise the latest event offset in that recording; activity
beyond it is ignored.

## 3. Matching and tie handling

There is no matching step: segment-level sets are compared directly. Ties and
ordering cannot affect the result. The only boundary convention is the
floor/ceil rule above; it is exact (no epsilon), and `ceil(offset / L)` means an
event ending exactly at a segment boundary stops at that boundary.

## 4. Aggregation, units and undefined values

`average="micro"` pools counts over all classes (the DCASE "overall" result).
`average="macro"` computes each ratio per class and averages over the classes
where that ratio is defined; as in the event-based metric, macro F1 is not the
harmonic mean of macro precision and recall, and the support of the three means
can differ.

Counts and units:

- `n_reference` is the number of active reference segments (summed over
  classes), not the number of segments in the recording.
- The error rate can exceed 1:

$$
ER = \frac{\cost{S + D + I}}{N_{\text{ref}}}
$$
- `substitution_rate`, `deletion_rate`, `insertion_rate` divide each count by
  the same `n_reference`.

A substitution is one segment in which both sides are active but no class
overlaps, yet it produces two class-level errors, so

$$
FP + FN = 2S + D + I
$$

Every rate and ratio is `None` when its denominator is zero: no reference
segments means no recall and no error rate; no predicted segments means no
precision. F1 is `0` when exactly one side is empty and `None` when both are.

## 5. Defaults and profiles

Defaults are `segment_length = 1.0` s and `average = "micro"`, matching the
`sed_eval`-style overall result used for DCASE segment-based scores. The segment
length is a profile parameter, not a universal constant: DCASE 2013-2016 used
1 s, other work uses 0.5 s or 0.1 s. Reports must state the value.

`sed_eval` truncates the evaluated roll to `ceil(max(event offset) / L)` unless
an explicit length is passed; this implementation uses recording durations when
they are supplied and reproduces the `sed_eval` default otherwise.

## 6. Hand-computed example

`L = 1 s`, duration 10 s.

References: class 0 at `[0.2, 2.1)` and `[5.0, 5.5)`, class 1 at `[3.0, 4.0)`.
Predictions: class 0 at `[0.5, 1.5)` and `[5.2, 5.4)`, class 1 at `[3.5, 4.2)`.

Active segments: class 0 reference `{0,1,2,5}`, class 0 prediction `{0,1,5}`,
class 1 reference `{3}`, class 1 prediction `{3,4}`.

- `TP = 4` (segments 0, 1, 5 for class 0 and 3 for class 1)
- `FP = 1` (segment 4, class 1), `FN = 1` (segment 2, class 0)
- precision = recall = F1 = `4/5 = 0.8`
- `S = 0`, `D = 1`, `I = 1`, error rate = `2/5 = 0.4`

Class 0: precision 1, recall 0.75, F1 `6/7`. Class 1: precision 0.5, recall 1,
F1 `2/3`.

## 7. Verification and complexity

- Parity: `tests/parity/test_segment_f1_sed_eval.py` compares TP/FP/FN, active
  reference/predicted segments, S/D/I and all rates against
  `sed_eval.SegmentBasedMetrics` on hand fixtures, a substitution case, exact
  boundaries, seeded random perturbations, 100 URBAN-SED test clips and 40
  AudioSet strong clips. Counts are exact; floats agree to `1e-12` (sed_eval
  computes F1 as `2PR/(P+R)`, so its last bits can differ).
- Divergence by design: `sed_eval` returns `NaN` for precision/F1 when the
  system output is empty and for F1 when one side of a class is empty; this
  implementation uses the `None`/zero policy in §4. The parity helper asserts
  the divergence explicitly instead of skipping it.
- Complexity: ranges are merged per (recording, class), then one sweep per
  recording over range boundaries; time is $O(E \log E + R \log R)$ in events and
  ranges, memory $O(E)$. When durations are supplied, each recording's duration is
  also found by a linear search, which adds a term quadratic in the number of
  recordings. No dense `[segments × classes]` matrix is built, so long recordings
  stay cheap.

## Limitations

- No per-class error-rate decomposition: `sed_eval` reports S/D/I only overall,
  and so does this implementation.
- Segment length must be uniform across the evaluated set; per-recording
  resolutions are not supported.
- Events only. For score grids see [frame metrics](frame_events.md); soft labels
  are not supported here.
