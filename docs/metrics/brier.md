---
title: "Brier score for sound event detection"
description: "The Brier score for aligned binary or soft targets: formula, penalty curve, weighting, interpretation and scikit-learn parity."
faq:
  - q: "Is a lower Brier score better?"
    a: "Yes. 0 is a perfect prediction of binary targets and 1 is the worst."
  - q: "Does SEDMetrics apply a sigmoid first?"
    a: "No. Inputs must already be probabilities between 0 and 1."
---

# Brier score for aligned targets, version 1

The Brier score is the weighted mean squared difference between predicted probabilities and targets. It runs from 0 to 1, and lower is better.

## What does the Brier score penalise?

The cost grows with the square of the distance between the predicted probability
and the target: a confident wrong answer costs far more than a hesitant one. The
red line is the penalty, and so is the red term in the formula.

<div class="pen" data-figure="brier"></div>

## Definition

This is a binary proper scoring rule evaluated independently for one class on
aligned targets and predictions. Both are finite probabilities in $[0, 1]$.
There is no implicit sigmoid, score calibration, or event-to-frame conversion.
Each frame has weight 1, or its duration in seconds when duration weighting is
selected. Finite, increasing nonnegative frame boundaries are required for the
latter. Empty inputs return `None`; invalid dimensions or values raise.

For targets $y_i$, probabilities $p_i$ and positive weights $w_i$, the score is
returned together with its numerator and weight:

$$
\mathrm{BS} = \frac{\sum_i w_i\, \cost{(p_i - y_i)^2}}{\sum_i w_i}
$$

The minimum is zero and the maximum is one. For a soft target $q$, this is the
squared distance to $q$. The expected loss over a Bernoulli outcome $Y$ adds a
constant that this score leaves out:

$$
\mathbb{E}\bigl[(p - Y)^2\bigr] = (p - q)^2 + q\,(1 - q)
$$

## Interpretation and verification

So the same prediction minimises both, while the reported values differ. Annotator agreement should not automatically be interpreted as a
well-calibrated population probability. Macro and micro averaging are not yet
offered. This is not a localization or alert-delay metric.

Example: targets `[1, 0]`, probabilities `[0.8, 0.1]`, equal weights yield
`(0.04 + 0.01)/2 = 0.025`. Binary target fixtures are compared with
`sklearn.metrics.brier_score_loss` with matching sample weights at `1e-12`.
Source: [Brier (1950)](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2).
