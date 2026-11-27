---
title: "Frame-based F1, AP and AUROC"
description: "Frame classification precision, recall, F1, average precision and AUROC on aligned labels and scores, with frame or duration weights."
faq:
  - q: "Do average precision and AUROC depend on the threshold?"
    a: "No. They depend on how the scores rank positive and negative frames, and on the frame weights."
  - q: "Is a score equal to the threshold positive?"
    a: "Yes."
---

# Binary frame classification, version 1

Frame-based metrics score one class frame by frame. Precision, recall and F1 compare thresholded scores with the labels. Average precision and AUROC measure how well the scores rank active frames above inactive ones.

## What do frame metrics penalise?

Every frame on the wrong side of the threshold costs the same. Move the threshold:
precision, recall and F1 react, while AP and AUROC, which only rank the frames,
stay put.

<div class="pen" data-figure="frame" data-scenarios="threshold"></div>

## Definition

Status: established binary classification definitions on an explicitly aligned
single-class track. References: [scikit-learn AP](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html)
and [AUROC](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html).

Inputs are Boolean labels and finite scores for one class, already aligned in
time and with equal length. This version does not convert events
to frame labels, infer recording coverage, or aggregate classes. A score can be
a logit or a probability; no sigmoid is applied. For multiple recordings callers
may concatenate only after validating their own coverage and alignment.

Threshold equality is positive. Frame $i$ is predicted active when

$$
\hat{y}_i = [\, s_i \ge \tau \,]
$$

Frame weighting sets $w_i = 1$; duration weighting uses $w_i = b_{i+1} - b_i$
from finite, strictly increasing nonnegative boundaries in seconds. Boundaries
must have one more element than labels. A zero-length input has undefined
metrics. The counts, in frame units or seconds, are

$$
TP = \sum_i w_i\, y_i \hat{y}_i, \qquad
FP = \sum_i w_i\, (1 - y_i)\, \hat{y}_i, \qquad
FN = \sum_i w_i\, y_i\, (1 - \hat{y}_i)
$$

$$
P = \frac{TP}{TP + \cost{FP}}, \qquad R = \frac{TP}{TP + \cost{FN}}, \qquad
F_1 = \frac{2\,TP}{2\,TP + \cost{FP + FN}}
$$

Zero denominators are `None`. Average precision sums the precision $P_k$ at each
descending distinct score, weighted by the increase in recall; ties are grouped,
and it is undefined without positive reference weight:

$$
AP = \sum_k (R_k - R_{k-1})\, P_k
$$

AUROC is the weighted probability that a positive frame scores above a negative
one, plus half the weight of ties. With $\mathcal{P}$ the positive and
$\mathcal{N}$ the negative frames, it is undefined unless both are present:

$$
\mathrm{AUROC} = \frac{
\sum_{i \in \mathcal{P}} \sum_{j \in \mathcal{N}} w_i w_j
\bigl( [s_i > s_j] + \tfrac12 [s_i = s_j] \bigr)}
{\sum_{i \in \mathcal{P}} w_i \; \sum_{j \in \mathcal{N}} w_j}
$$

The AP undefined convention differs from scikit-learn's no-positive convention.
Threshold is required; weighting defaults to frame count. No averaging profile
is implied.

Example: labels `[True, False, True]`, scores `[0.9, 0.8, 0.1]`, threshold
`0.5`: TP=1, FP=1, FN=1, TN=0, precision=recall=F1=0.5,
AP=(1+2/3)/2=5/6, AUROC=1/2. Duration weights change these quantities.
Sorting costs $O(n \log n)$. Tests use hand examples and compare with scikit-learn
on supported binary cases; see the parity test for tolerance and dependency.
