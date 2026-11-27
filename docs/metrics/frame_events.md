---
description: Map reference sound events to frame intervals and calculate classwise metrics.
---

# Frame evaluation from events, version 1

Uses the binary definitions and undefined values in [frame_binary.md](frame_binary.md).
Each score interval is labeled positive for a class if it has strictly positive
overlap with at least one same-class reference event in the recording. Intervals
are half-open, so touching endpoints alone do not count. This *any-overlap*
policy can amplify very short events; it is an explicit SEDMetrics convention,
not a claim of universal benchmark parity.

Inputs require every evaluated recording and duration, including recordings with
no events; one score track must cover each full recording from zero to its exact
duration. All tracks must have the same explicit nonempty class vocabulary.
Every reference must use a known recording and class, have valid boundaries,
and fit the recording. Scores must be finite, with one score per frame per
class. Threshold equality is active. Frame and duration weighting follow the
binary specification.

Classwise results include absent reference classes: AP and AUROC are undefined
as specified in frame_binary. Macro computes the unweighted mean separately for
each metric over classes where that metric is defined. Micro pools all
frame-class samples, including durations once per class, then computes each
metric; it is not the mean of classwise metrics. Per-class counts and pooled
counts are returned. There is no implicit class vocabulary or resampling.

Example: boundaries `[0, 1, 2]`, reference `[0.9, 1.0)` activates only the
first frame. With scores `[0.8, 0.2]` and threshold 0.5, TP=1 and TN=1.
Overlapping reference events do not add duplicate positives. Mapping currently
uses a direct frame-by-event scan, O(frames × events × classes), followed by
sorting for AP/AUROC. Reference-label and pooled-score fixtures should be
compared with an independent implementation; no event-to-frame parity claim is
made for a particular external benchmark.
