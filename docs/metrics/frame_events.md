---
title: "Frame metrics from sound events"
description: "Map reference sound events to frame labels by any positive overlap, then compute classwise, micro and macro frame metrics."
faq:
  - q: "When is a frame labelled positive?"
    a: "When it has strictly positive overlap with at least one reference event of the same class."
---

# Frame evaluation from events, version 1

Frame evaluation from events turns reference events into frame labels: a frame is positive when a reference of that class overlaps it. SEDMetrics then reports classwise, micro and macro frame metrics for multi-class score tracks.

## How do late scores affect frame metrics?

A score curve that is right but late loses frames at both ends of every event,
and its ranking degrades with it. Delay the scores and watch all five numbers.

<div class="pen" data-figure="frame" data-scenarios="shift"></div>

## Label mapping

Uses the binary definitions and undefined values in [frame_binary.md](frame_binary.md).
The score interval $[b_i, b_{i+1})$ is labelled positive for class $c$ if it has
strictly positive overlap with at least one same-class reference event $G$ in the
recording:

$$
y_{i,c} = \Bigl[\, \exists\, G \in \mathcal{G}_c :\;
\min(b_{i+1}, G_{\text{off}}) - \max(b_i, G_{\text{on}}) > 0 \,\Bigr]
$$

Intervals are half-open, so touching endpoints alone do not count. This
*any-overlap* policy can amplify very short events; it is an explicit SEDMetrics
convention, not a claim of universal benchmark parity.

Inputs require every evaluated recording and duration, including recordings with
no events; one score track must cover each full recording from zero to its exact
duration. All tracks must have the same explicit nonempty class vocabulary.
Every reference must use a known recording and class, have valid boundaries,
and fit the recording. Scores must be finite, with one score per frame per
class. Threshold equality is active. Frame and duration weighting follow the
binary specification.

## Aggregation

Classwise results include absent reference classes: AP and AUROC are undefined
as specified in frame_binary. Macro computes the unweighted mean separately for
each metric over classes where that metric is defined. Micro pools all
frame-class samples, including durations once per class, then computes each
metric; it is not the mean of classwise metrics. Per-class counts and pooled
counts are returned. There is no implicit class vocabulary or resampling.

## Example, cost and verification

Boundaries `[0, 1, 2]` with the reference `[0.9, 1.0)` activate only the first
frame. With scores `[0.8, 0.2]` and threshold 0.5, TP=1 and TN=1. Overlapping
reference events do not add duplicate positives.

Mapping currently uses a direct frame-by-event scan,
$O(\text{frames} \times \text{events} \times \text{classes})$, followed by
sorting for AP and AUROC. Reference-label and pooled-score fixtures should be
compared with an independent implementation; no event-to-frame parity claim is
made for a particular external benchmark.
