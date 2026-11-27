# Brier score for aligned targets, version 1

This is a binary proper scoring rule evaluated independently for one class on
aligned targets and predictions. Both are finite probabilities in `[0, 1]`.
There is no implicit sigmoid, score calibration, or event-to-frame conversion.
Each frame has weight 1, or its duration in seconds when duration weighting is
selected. Finite, increasing nonnegative frame boundaries are required for the
latter. Empty inputs return `None`; invalid dimensions or values raise.

For targets `y_i`, probabilities `p_i`, and positive weights `w_i`, return
`sum(w_i * (p_i - y_i)^2) / sum(w_i)` together with the numerator and weight.
The minimum is zero and the maximum is one. For a soft target `q`, this is the
squared distance to `q`; expected Brier loss over a Bernoulli outcome adds the
constant `q(1-q)`. Thus the minimizer is the same but the reported values are
not the same. Annotator agreement should not automatically be interpreted as a
well-calibrated population probability. Macro and micro averaging are not yet
offered. This is not a localization or alert-delay metric.

Example: targets `[1, 0]`, probabilities `[0.8, 0.1]`, equal weights yield
`(0.04 + 0.01)/2 = 0.025`. Binary target fixtures are compared with
`sklearn.metrics.brier_score_loss` with matching sample weights at `1e-12`.
Source: [Brier (1950)](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2).
