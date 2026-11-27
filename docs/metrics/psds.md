# PSDS — Polyphonic Sound Detection Score

Status: **implemented** for the intersection-based DTC/GTC/CTTC criteria.
Parity with `sed_scores_eval` 0.0.4 is tested, including per-class curves.

Sources: Bilen et al., *A Framework for the Robust Evaluation of Sound Event
Detection*, ICASSP 2020, <https://arxiv.org/abs/1910.08440>; Ebbers et al.,
*Threshold-Independent Evaluation of Sound Event Detection Scores*,
<https://arxiv.org/abs/2201.13148>; the `sed_scores_eval` 0.0.4 implementation
as the reference oracle; DCASE Task 4 PSDS1/PSDS2 profiles.

## 1. Name, status, input representation

PSDS measures detection quality **independently of a chosen threshold** by
sweeping over the score range and integrating the resulting precision/recall
envelope. It is an established metric; the specific parameter sets are branded
as PSDS1 and PSDS2.

Inputs:

- References: events `(recording_id, class_id, onset, offset)` in seconds,
  half-open, positive length, inside their recording.
- Score tracks: per recording, a strictly increasing boundary vector of length
  `T + 1` and a `T × C` score matrix named by class id. Frame `i` covers
  `[boundaries[i], boundaries[i+1])`. Scores must be finite; `NaN` and `-inf`
  are rejected (see Limitations).
- Recording durations: required. They define the exposure in the eFPR and are
  validated to contain the events and the score grid.
- The scored classes and the referenced classes must be the **same set**, and
  every scored class needs at least one reference event.

## 2. Definition

At a threshold `τ`, the detections of a class in a clip are the maximal runs of
frames with `score >= τ`; a run `[t_on, t_off)` yields a detection
`D = [boundaries[t_on], boundaries[t_off])`. There is no threshold list: every
distinct score value is an operating point, and statistics are accumulated over
all of them.

Rounded comparisons (`round_d` = round half-to-even to `d` decimals, `d = 6`
by default):

```
I(D, G) = max(0, min(D.off, G.off) - max(D.on, G.on))

DTC(D) = Σ_{G ∈ same-class refs} I(D, G)  >=  dtc_threshold · |D|
GTC(G) = Σ_{D : DTC(D)} I(D, G)          >=  gtc_threshold · |G|
CT(D, k) = ¬DTC(D) ∧ Σ_{H ∈ refs of class k} I(D, H) >= cttc_threshold · |D|

TP_c(τ) = #{G of class c : GTC(G)}
FP_c(τ) = #{D of class c} - #{D of class c : DTC(D)}
CT_c,k(τ) = #{D of class c : CT(D, k)}

TPR_c(τ) = TP_c(τ) / n_ref_c
FPR_c(τ) = FP_c(τ) / Σ_recordings duration
CTR_c,k(τ) = CT_c,k(τ) / max(Σ_{G ∈ k} |G|, 1e-12)
eFPR_c(τ) = ( FPR_c(τ) + alpha_ct · mean_{k ≠ c} CTR_c,k(τ) ) · unit
```

with `unit` = 1, 60 or 3600 for second, minute or hour.

Around this family of operating points:

1. Per class, sort points by `(eFPR, TPR)`, keep the Pareto frontier (strictly
   increasing TPR), keep the highest TPR of each duplicated eFPR, and truncate
   at `max_efpr`.
2. Take the union of all per-class eFPR values as the macro grid and evaluate
   each class's frontier as a **right-continuous step function** (value at the
   last knot `<= x`, 0 below the first knot, last value above the last knot).
3. Macro TPR: `mean_c TPR_c(e) - alpha_st · std_c TPR_c(e)` (population std),
   clamped at 0. Append a final point at `max_efpr`.
4. `PSDS = (1 / max_efpr) · Σ_i TPR(e_i) · (e_{i+1} - e_i)` over the sorted
   grid — a **left-endpoint staircase integral**, not a trapezoid rule.

This is the intersection-based formulation: no IoU, no one-to-one assignment,
and a detection can be "relevant" while contributing to several references.

## 3. Matching, thresholds and ties

- There is no matching step and no tie-breaking assignment. DTC is a per
  detection inequality on the summed intersection; GTC is a per reference
  inequality over DTC-relevant detections. Multiple detections may contribute to
  one reference and one detection may contribute to several references.
- Threshold equality **activates** a frame (`score >= τ`); a frame with a score
  equal to τ belongs to the detection.
- Every distinct score is an operating point, so ties are handled by evaluating
  the shared value once; a plateau of equal scores is one detection.
- Comparisons round both sides to `time_decimals` (default 6) before `>=`, which
  gives an effective tolerance of half a unit in the last kept decimal on the
  **summed** intersection. Individual intersections and lengths are not rounded.
- The "no detection" operating point (all statistics zero) is always present as
  a synthetic `+inf` threshold.

## 4. Aggregation, units and undefined values

- Macro over classes with equal weight; `alpha_st` subtracts the across-class
  standard deviation (PSDS2/DCASE use 1.0). There is no micro variant.
- Exposure is the sum of all recording durations, not the per-class activity
  duration.
- Every scored class must have references and vice versa; there is no
  `None`-per-class fallback. Invalid inputs raise instead of producing an
  undefined score.
- `PSDS` is in `[0, 1]` for a valid configuration. Empty per-class frontiers
  (possible only with a degenerate `max_efpr`) contribute 0.

## 5. Defaults and profiles

The defaults are the **PSDS1** profile, with the DCASE 2023/2024 settings:

| | DTC | GTC | CTTC | alpha_ct | alpha_st | max eFPR |
| --- | --- | --- | --- | --- | --- | --- |
| PSDS1 | 0.7 | 0.7 | — | 0.0 | 1.0 | 100 / hour |
| PSDS2 | 0.1 | 0.1 | 0.3 | 0.5 | 1.0 | 100 / hour |

`alpha_st` must be passed as 1.0. `sed_scores_eval` defaults `alpha_st` to 0.0,
and the local `YOLIO-WOLRD/src/metrics.py` wrapper also defaults it to 0.0
while describing the result as PSDS1 — that is not the DCASE PSDS1 definition.
Parity tests here pass every parameter explicitly.

`cttc_threshold` must be set exactly when `alpha_ct > 0`; the implementation
rejects the mismatched combinations that `sed_scores_eval` also rejects.

## 6. Hand-computed example

One recording, 4 s, one class, 1 s frames, scores `[0.1, 0.9, 0.1, 0.9]`,
reference `[1.0, 2.0)`, `dtc = gtc = 0.5`, `alpha_st = 0`, unit seconds,
`max_efpr = 1`.

- `τ = 0.9`: detections `[1,2)` and `[3,4)`. The first is DTC-relevant
  (`1.0 >= 0.5·1`), the second is not (`0 >= 0.5`). So `TP = 1`, `FP = 1`,
  `eFPR = 1/4 = 0.25`, `TPR = 1`.
- `τ = 0.1`: one detection `[0,4)`. It intersects the reference by 1 s, but
  `1.0 >= 0.5·4 = 2.0` fails, so it is a false positive: `TPR = 0`, `eFPR = 1/4`.
- No detections: `(0, 0)`.

Frontier: `(0, 0)` and `(0.25, 1)`. The staircase integral from 0 to 1 is
`1 · (1 - 0.25) = 0.75`, so `PSDS = 0.75`.

Note that the second threshold produces no true positive: the criterion rewards
a detection whose intersection with references covers half of the **detection**
length, not half of the reference.

## 7. Verification and complexity

- Parity: `tests/parity/test_psds_sed_scores_eval.py` compares against
  `sed_scores_eval.intersection_based.psds` 0.0.4 on synthetic multi-clip score
  matrices: PSDS1-style thresholds, CTTC with `alpha_ct = 0.5`, `alpha_st = 0`
  and `1`, quantized scores with plateaus, and per-class curves compared
  elementwise to `1e-12`. Scalar agreement is `1e-9`.
- The oracle requires NumPy/SciPy/pandas with writable buffers
  (`pandas < 3`); the parity extra pins them. Tests are skipped when the oracle
  environment is unavailable.
- Rust-level tests cover the hand example, the no-detection case, cross-trigger
  accounting, malformed tracks, configuration conflicts and boundedness.
- Complexity: per class and clip, `U` distinct thresholds are scanned over `T`
  frames and `R` references, i.e. `O(U · T + U · T · R)` per class/clip, with
  `U <= T`. This is the straightforward formulation; the reference
  implementation's incremental variant is faster on long recordings, and this is
  the main performance gap.

## Limitations

- Non-finite scores (`NaN`, `-inf`) are rejected. `sed_scores_eval` defines
  special semantics for both (NaN freezes a detection, `-inf` is a hard off);
  reproducing them is deliberately out of scope until a use case requires it.
- No per-clip class-column equality requirement: a class may be scored in some
  clips only. The reference requires identical columns all clips; reports that
  rely on this difference are not comparable.
- No CTTC on single-class datasets in the reference implementation (it crashes);
  here `alpha_ct > 0` with one class reduces to the mean over zero other classes,
  i.e. no cross-trigger term.
- No piPSDS, no bootstrapped PSDS, no score-grid resampling. PSDS1/PSDS2 presets
  are documented parameter sets, not separate functions.
