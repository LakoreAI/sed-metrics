---
title: "PSDS: polyphonic sound detection score"
description: "PSDS formulas, DTC, GTC and cross-trigger criteria, PSDS1 and PSDS2 profiles, penalties and parity with sed_scores_eval."
faq:
  - q: "What is the difference between PSDS1 and PSDS2?"
    a: "PSDS1 requires 70% on both overlap criteria and has no cross-trigger term. PSDS2 requires 10%, counts cross-triggers from 30% overlap and weights them by 0.5."
  - q: "Does PSDS depend on a decision threshold?"
    a: "No. Distinct score values are evaluated as operating points and the score integrates over them."
  - q: "What does alpha_st do?"
    a: "It subtracts the standard deviation of the true-positive rate across classes, so uneven performance lowers the score. The default is 1.0."
---

# PSDS: polyphonic sound detection score

The polyphonic sound detection score (PSDS) rates a sound event detector across its decision thresholds. At each one it checks how much of every detection lies on a reference and how much of every reference is covered. The score is the normalised area under the curve of effective true-positive rate against false positives.

Specification identifier: `psds/1`.

Status: implemented for the intersection-based DTC/GTC/CTTC criteria.
Parity with `sed_scores_eval` 0.0.4 is tested, including per-class curves.

Sources: Bilen et al., *A Framework for the Robust Evaluation of Sound Event
Detection*, ICASSP 2020, <https://arxiv.org/abs/1910.08440>; Ebbers et al.,
*Threshold-Independent Evaluation of Sound Event Detection Scores*,
<https://arxiv.org/abs/2201.13148>; the `sed_scores_eval` 0.0.4 implementation
as the reference oracle; DCASE Task 4 PSDS1/PSDS2 profiles.

## What does PSDS penalise?

PSDS sweeps every threshold and asks, at each one, which detections are mostly
inside a reference and which references are mostly covered. The score is the area
under the resulting curve, so a penalty is area lost: the hatched region. In
the formulas, red terms push the score down.

<div class="pen" data-figure="psds"></div>

| Mistake | PSDS1 (70% / 70%) | PSDS2 (10% / 10%, cross-triggers) |
| --- | --- | --- |
| Detection too long or too short | Lost once less than 70% overlaps | Tolerated down to 10% |
| Hole in a detection | Free until covered share drops below 70% | Free until below 10% |
| False alarm above the true detection's score | Area left of its false-positive rate is lost | Same |
| One class much worse than another | Standard deviation across classes is subtracted | Same |
| False detection on another class's event | An ordinary false positive | A false positive plus a cross-trigger charge |

!!! warning "The lowest threshold is an operating point too"

    At a threshold at or below every score, each recording becomes one long
    detection per class. That is at most one false positive per recording,
    however long the recording is. An
    always-on detector can therefore score well when the audio sits in few, long
    recordings and an event covers at least `dtc_threshold` of its clip. Try
    *Always-on detector* above, and report how the audio was split.

## PSDS1 and PSDS2

PSDS1 and PSDS2 are one metric with two parameter sets. PSDS1 asks for tight
localisation: 70% on both overlap criteria and no cross-trigger charge. PSDS2
accepts loose localisation at 10% and charges for confusing one class with
another. [Section 5](#5-defaults-and-profiles) lists every parameter.

The two differ in the effective false-positive rate. PSDS1 counts false
positives only:

$$
e_c^{\text{PSDS1}}(\tau) = U\, \cost{\frac{FP_c(\tau)}{T}}
$$

PSDS2 adds the mean cross-trigger rate over the other classes, weighted by 0.5:

$$
e_c^{\text{PSDS2}}(\tau) = U \left( \cost{\frac{FP_c(\tau)}{T}} +
\cost{\frac{0.5}{C - 1} \sum_{k \ne c} \frac{CT_{c,k}(\tau)}{L_k}} \right)
$$

The defaults compute PSDS1. For PSDS2, pass its four parameters. In this example
the class 0 detector also fires on the class 1 event, and one hour of audio is
split into 10 s recordings:

```python
from sedmetrics import SEDMetrics

references = [(0, 0, 1.0, 4.0), (0, 1, 6.0, 9.0)]
scores = {0: ([0.0, 1.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0],
              {0: [0.0, 0.7, 0.0, 0.0, 0.9, 0.0, 0.0],
               1: [0.0, 0.0, 0.0, 0.7, 0.7, 0.7, 0.0]})}
scores.update({i: ([0.0, 10.0], {0: [0.0], 1: [0.0]}) for i in range(1, 360)})
common = dict(metric="psds", recordings={i: 10.0 for i in range(360)}, scores=scores)

psds1 = SEDMetrics.eval(references, **common)
psds2 = SEDMetrics.eval(references, **common, dtc_threshold=0.1, gtc_threshold=0.1,
                        cttc_threshold=0.3, alpha_ct=0.5)
print(round(psds1.psds, 3), round(psds2.psds, 3))  # 0.99 0.0
```

PSDS1 loses 1% for one false positive in an hour. The same detection is also a
cross-trigger on 3 s of the other class, which PSDS2 prices at 600 per hour, far
past the limit of 100. The figure above shows both curves for each mistake.

## 1. Name, status, input representation

PSDS measures detection quality independently of a chosen threshold by
sweeping over the score range and integrating the resulting PSD-ROC
envelope. It is an established metric; the specific parameter sets are branded
as PSDS1 and PSDS2.

Inputs:

- References: events `(recording_id, class_id, onset, offset)` in seconds,
  half-open, positive length, inside their recording.
  [Overlapping and touching references](#overlapping-and-touching-references) of
  one class are merged.
- Score tracks: per recording, a strictly increasing boundary vector of length
  `T + 1` and a `T × C` score matrix named by class id. Frame `i` covers
  `[boundaries[i], boundaries[i+1])`. Scores must be finite; `NaN` and `-inf`
  are rejected (see Limitations).
- Recording durations: required. They define the exposure in the eFPR and are
  validated to contain the events and the score grid.
- Every recording must have one score track covering exactly `[0, duration]`,
  and each track must contain every evaluated class. Partial coverage and
  omitted tracks now raise an error; callers using previous versions must supply
  complete tracks. No implicit values are inserted.
- The scored classes and the referenced classes must be the same set, and
  every scored class needs at least one reference event.

### Overlapping and touching references

Within a recording, references of one class that overlap or touch are merged
into one event before anything is counted. The criteria sum intersections over
references, so shared time would otherwise count twice. The reference count
$N_c$ (`n_reference`), the total reference duration $L_k$
(`reference_duration`) and every criterion describe the merged events.
`sed_scores_eval` rejects such input and asks for the same merge.

!!! warning "Changed in 0.1.2"

    Release 0.1.1 did not merge. A detection covering 40% of itself failed the
    PSDS1 detection criterion against one reference and passed it when that
    reference was listed twice. Rescore results computed from references with
    overlapping or touching events of one class.

Event, segment and frame metrics are not changed by this rule.

## 2. Definition

At a threshold $\tau$, the detections of class $c$ in a clip are the maximal
runs of frames with score $\ge \tau$; a run $[t_{\text{on}}, t_{\text{off}})$
yields a detection $D$ between those frame boundaries. There is no threshold
list: every distinct score value is an operating point, and statistics are
accumulated over all of them.

!!! deviation "Current behaviour: scores are 32-bit floats"

    The binding converts every score to `f32` before thresholding. Two scores
    closer than that resolution become one operating point: in a two-frame
    example, `0.5` and `0.500000001` score 0.0 where `0.5` and `0.6` score 1.0.
    A finite value beyond the `f32` range, such as `1e39`, is rejected as
    non-finite.

With the intersection of a detection and a reference

$$
I(D, G) = \max\bigl(0,\; \min(D_{\text{off}}, G_{\text{off}}) - \max(D_{\text{on}}, G_{\text{on}})\bigr)
$$

the three criteria are, with $\mathcal{G}_c$ the references of class $c$ in the clip:

$$
\mathrm{DTC}(D):\quad \sum_{G \in \mathcal{G}_c} I(D, G) \;\ge\; \rho_{\text{DTC}}\,\lvert D \rvert
$$

$$
\mathrm{GTC}(G):\quad \sum_{D \,:\, \mathrm{DTC}(D)} I(D, G) \;\ge\; \rho_{\text{GTC}}\,\lvert G \rvert
$$

$$
\mathrm{CT}_{c,k}(D):\quad \neg\,\mathrm{DTC}(D) \;\wedge\;
\sum_{H \in \mathcal{G}_k} I(D, H) \;\ge\; \rho_{\text{CTTC}}\,\lvert D \rvert
$$

Both sides of every comparison are rounded half-to-even to `time_decimals`
places (6 by default).

Counts and rates. $TP_c(\tau)$ is the number of references of class $c$
that satisfy GTC, $FP_c(\tau)$ the number of its detections that fail DTC, and
$CT_{c,k}(\tau)$ the number that cross-trigger on class $k$. With $N_c$
references of class $c$, $T$ the total audio duration in seconds, $L_k$ the total
reference duration of class $k$, $C$ classes and $U \in \{1, 60, 3600\}$ for
second, minute or hour:

$$
r_c(\tau) = \frac{TP_c(\tau)}{N_c}
$$

$$
e_c(\tau) = U \left( \cost{\frac{FP_c(\tau)}{T}} +
\cost{\frac{\alpha_{\text{CT}}}{C - 1} \sum_{k \ne c}
\frac{CT_{c,k}(\tau)}{\max(L_k,\, 10^{-12})}} \right)
$$

Around this family of operating points:

1. Per class, sort points by $(e, r)$, keep the Pareto frontier (strictly
   increasing $r$), keep the highest $r$ of each duplicated $e$, and truncate at
   $e_{\max}$ (`max_efpr`).
2. Take the union of all per-class $e$ values as the macro grid
   $e_1 < \dots < e_J$ and evaluate each class's frontier as a
   right-continuous step function (value at the last knot $\le x$, 0 below
   the first knot, last value above the last knot).
3. With $\mu(e)$ and $\sigma(e)$ the mean and population standard deviation of
   those values across classes, the effective true-positive rate is

    $$
    \tilde{r}(e) = \max\bigl(0,\; \mu(e) - \cost{\alpha_{\text{ST}}\,\sigma(e)}\bigr)
    $$

4. Integrate the staircase from the left endpoints, with $e_{J+1} = e_{\max}$:

    $$
    \mathrm{PSDS} = \frac{1}{e_{\max}} \sum_{j=1}^{J} \tilde{r}(e_j)\,\bigl(e_{j+1} - e_j\bigr)
    $$

This is the intersection-based formulation: no IoU, no one-to-one assignment,
and a detection can be "relevant" while contributing to several references.

## 3. Matching, thresholds and ties

- There is no matching step and no tie-breaking assignment. DTC is a per
  detection inequality on the summed intersection; GTC is a per reference
  inequality over DTC-relevant detections. Multiple detections may contribute to
  one reference and one detection may contribute to several references.
- Threshold equality activates a frame (`score >= τ`); a frame with a score
  equal to τ belongs to the detection.
- Every distinct score is an operating point, so ties are handled by evaluating
  the shared value once; a plateau of equal scores is one detection.
- Comparisons round both sides to `time_decimals` (default 6) before `>=`.
  Individual intersections and lengths are not rounded before summation.
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

The defaults are the PSDS1 profile, with the DCASE 2023/2024 settings:

| | DTC | GTC | CTTC | alpha_ct | alpha_st | max eFPR |
| --- | --- | --- | --- | --- | --- | --- |
| PSDS1 | 0.7 | 0.7 | none | 0.0 | 1.0 | 100 / hour |
| PSDS2 | 0.1 | 0.1 | 0.3 | 0.5 | 1.0 | 100 / hour |

The default here is `alpha_st = 1.0`, as the DCASE profiles require.
`sed_scores_eval` defaults it to 0.0, so a call that relies on that default does
not compute DCASE PSDS1. Parity tests here pass every parameter explicitly.

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
a detection whose intersection with references covers half of the detection
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
- Complexity: per class and clip, $U$ distinct thresholds are scanned over $T$
  frames and $R$ references, i.e. $O(UT + UTR)$ per class and clip, with
  $U \le T$. This is a straightforward formulation. The reference implementation
  uses an incremental method; relative performance has not been benchmarked.

## Limitations

- Non-finite scores (`NaN`, `-inf`) are rejected. `sed_scores_eval` defines
  special semantics for both (NaN freezes a detection, `-inf` is a hard off);
  reproducing them is deliberately out of scope until a use case requires it.
- No CTTC on single-class datasets in the reference implementation (it crashes);
  here `alpha_ct > 0` with one class reduces to the mean over zero other classes,
  i.e. no cross-trigger term.
- No bootstrapped PSDS or score-grid resampling. piPSDS is described in
  [pipsds.md](pipsds.md). PSDS1/PSDS2 presets
  are documented parameter sets, not separate functions.
