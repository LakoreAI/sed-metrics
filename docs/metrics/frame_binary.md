---
description: Frame classification precision, recall, F1, average precision and AUROC.
---

# Binary frame classification, version 1

Status: established binary classification definitions on an explicitly aligned
single-class track. References: [scikit-learn AP](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.average_precision_score.html)
and [AUROC](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.roc_auc_score.html).

Inputs are Boolean labels and finite scores for one class, already aligned in
time and with equal length. This version deliberately does not convert events
to frame labels, infer recording coverage, or aggregate classes. A score can be
a logit or a probability; no sigmoid is applied. For multiple recordings callers
may concatenate only after validating their own coverage and alignment.

Threshold equality is positive (`score >= threshold`). Frame weighting counts
each frame once; duration weighting uses positive differences between supplied
finite, strictly increasing nonnegative boundaries in seconds. Boundaries must
have one more element than labels. A zero-length input has undefined metrics.
Counts use frame units or seconds, respectively.

Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN).
Zero denominators are `None`. AP is the sum of precision at each descending
distinct score weighted by the increase in recall; ties are grouped, and it is
undefined without positive reference weight. AUROC is the weighted probability
that a positive scores above a negative, plus half the weight of ties, and is
undefined without both reference classes. The AP undefined convention differs
from scikit-learn's no-positive convention. Threshold is required; weighting
defaults to frame count. No averaging profile is implied.

Example: labels `[True, False, True]`, scores `[0.9, 0.8, 0.1]`, threshold
`0.5`: TP=1, FP=1, FN=1, TN=0, precision=recall=F1=0.5,
AP=(1+2/3)/2=5/6, AUROC=1/2. Duration weights change these quantities.
Sorting costs O(n log n). Tests use hand examples and compare with scikit-learn
on supported binary cases; see the parity test for tolerance and dependency.
