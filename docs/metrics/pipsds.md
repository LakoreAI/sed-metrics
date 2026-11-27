---
title: "piPSDS: post-processing independent PSDS"
description: "piPSDS takes the upper envelope of PSDS curves over supplied post-processings. Definition, formula, limits and parity evidence."
faq:
  - q: "Is piPSDS the score of one deployable system?"
    a: "No. The envelope can use a different post-processing for each class and false-positive rate."
---

# Post-processing independent PSDS

piPSDS is the post-processing independent form of PSDS. It evaluates several processed versions of a detector's scores and keeps, for each class and false-positive rate, the highest true-positive rate among them.

Status: established envelope for a finite, explicitly supplied set of
post-processed score tracks. Source: Ebbers et al. (2023),
<https://arxiv.org/abs/2306.15440>; oracle: `sed_scores_eval` 0.0.4.

## What does piPSDS penalise?

piPSDS only charges for what no supplied processing can achieve. Switch
processings in and out: the black curve is the envelope, the others are the
single PSDS curves.

<div class="pen" data-figure="pipsds"></div>

## Definition

Each configuration supplies complete score tracks for the same reference events,
recordings, class vocabulary and PSDS settings; inputs follow
[psds.md](psds.md). For each configuration $m \in \mathcal{M}$ compute the
intersection-based per-class PSDS curve $r_c^{(m)}(e)$ across all distinct finite
score thresholds. At each classwise false-positive rate take the maximum, using
the right-continuous staircase:

$$
r_c^{\ast}(e) = \max_{m \in \mathcal{M}} r_c^{(m)}(e)
$$

Then aggregate across classes and integrate as PSDS does, up to
$e_{\max}$ (`max_efpr`):

$$
\mathrm{piPSDS} = \frac{1}{e_{\max}} \int_0^{e_{\max}}
\max\bigl(0,\; \mu^{\ast}(e) - \cost{\alpha_{\text{ST}}\,\sigma^{\ast}(e)}\bigr)\, de
$$

where $\mu^{\ast}$ and $\sigma^{\ast}$ are the mean and population standard
deviation of $r_c^{\ast}(e)$ over classes. Threshold equality, tie handling,
rounding, units and unsupported cases are inherited from [psds.md](psds.md). At
least one configuration is required.

## Limits and verification

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
