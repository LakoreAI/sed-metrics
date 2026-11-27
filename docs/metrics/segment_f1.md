# Segment-based precision, recall, F1 and error rate

Specification identifier: `segment_f1/1`.

Status: **implemented**. Established metric family; parity with `sed_eval` 0.2.1
is tested.

Source: Mesaros, Heittola and Virtanen, *Metrics for Polyphonic Sound Event
Detection*, Applied Sciences 6(6):162, 2016,
<https://doi.org/10.3390/app6060162>, and the segment-based evaluation in
`sed_eval` 0.2.1.

## 1. Input representation

Events `(recording_id, class_id, onset, offset)` in seconds, half-open
`[onset, offset)`, positive length, identical to the event-based metric.
Optional recording durations `{recording_id: duration_seconds}` define the
evaluated window. Malformed events and events outside their recording are
rejected, never clipped silently.

## 2. Definition

A segment is `S_k = [k·L, (k+1)·L)` for segment length `L` (`segment_length`,
default 1 s). Segment `k` is **active for class c** in a reference or prediction
set when at least one event of class c overlaps `S_k`. In indices this is
exactly

```
start = floor(onset / L)
end   = ceil(offset / L)
active = {start, ..., end - 1}
```

so an event that only touches a boundary does not activate the neighbouring
segment.

For each segment with reference active-class count `n_ref`, predicted count
`n_sys` and overlap `n_both`:

```
TP += n_both
FP += n_sys - n_both
FN += n_ref - n_both
S  += min(n_ref, n_sys) - n_both
D  += max(0, n_ref - n_sys)
I  += max(0, n_sys - n_ref)
```

with the sums taken over segments and then over recordings. Per class the same
counts are accumulated for that class only. The evaluated window of a recording
is its supplied duration, otherwise the latest event offset in that recording;
activity beyond it is ignored.

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

- `n_reference` is the number of **active reference segments** (summed over
  classes), not the number of segments in the recording.
- `error_rate = (S + D + I) / n_reference`; it can exceed 1.
- `substitution_rate`, `deletion_rate`, `insertion_rate` divide each count by
  the same `n_reference`.

A substitution is one segment in which both sides are active but no class
overlaps, yet it produces two class-level errors, so

```
FP + FN = 2·S + D + I
```

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
  recording over range boundaries; time is `O(E log E + R log R)` in events and
  ranges, memory `O(E)`. No dense `[segments × classes]` matrix is built, so
  long recordings stay cheap.

## Limitations

- No per-class error-rate decomposition: `sed_eval` reports S/D/I only overall,
  and so does this implementation.
- Segment length must be uniform across the evaluated set; per-recording
  resolutions are not supported.
- No frame metrics on an arbitrary score grid yet, and no soft labels.
