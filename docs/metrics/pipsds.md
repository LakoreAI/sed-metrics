# Post-processing independent PSDS

Status: established envelope for a finite, explicitly supplied set of
post-processed score tracks. Source: Ebbers et al. (2023),
<https://arxiv.org/abs/2306.15440>; oracle: `sed_scores_eval` 0.0.4.

Each configuration supplies complete score tracks for the same reference events,
recordings, class vocabulary and PSDS settings; inputs follow `psds.md`. For
each configuration compute the intersection-based per-class PSDS curve across
all distinct finite score thresholds. At each classwise eFPR take the maximum
TPR across configurations, using the right-continuous staircase. Then aggregate
classwise values with the PSDS mean minus `alpha_st` times population standard
deviation, clip below zero, and integrate the resulting staircase up to
`max_efpr`. Threshold equality, tie handling, rounding, units and unsupported
cases are inherited from `psds.md`. At least one configuration is required.

The envelope can choose a different configuration per class and per eFPR; it
is not a single deployable policy. Tracks may be noncausal: the caller must
record processing and actual decision time separately. The caller supplies
processed tracks explicitly; no filter is implied. One configuration reduces
to the existing PSDS. For a hand example, a one-class configuration with
frontier `(0,0), (0.25,1)` over eFPR `[0,1]` gives 0.75; adding a perfect
frontier `(0,1)` gives piPSDS 1.0. Results inherit the straightforward PSDS
computational complexity per configuration plus envelope merging.

Parity fixtures compare the scalar and classwise envelopes to the pinned
reference. This evaluates the finite supplied configuration set, not all
possible post-processings.
