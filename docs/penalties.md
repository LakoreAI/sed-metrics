---
title: "How SED metrics penalise mistakes"
description: "One table shows what event F1, segment F1, error rate, frame F1, PSDS1 and PSDS2 charge for the same sound event detection mistakes."
faq:
  - q: "Which metric is strictest about timing?"
    a: "In this comparison, event F1. Onsets 0.4 s late take it to zero while segment F1 and both PSDS profiles stay at 1."
  - q: "Why can PSDS ignore a late onset?"
    a: "PSDS asks how much of a detection and a reference overlap. A short delay leaves the overlap above its threshold."
---

# How metrics penalise mistakes

The same mistake can cost everything under one metric and nothing under another.
Each row below is one detector output, scored by the library against the same
three reference events. Deeper red means more of the score is lost. Select a row
to see the events.

<div class="pen" data-figure="matrix"></div>

## What the table shows

- Onsets 0.4 s late take event F1 to zero. Segment F1, the segment error rate
  and both PSDS profiles do not move.
- Splitting one event costs event F1 heavily. Segment metrics do not see the
  0.5 s hole, because every 1 s segment it touches still holds some detection.
- Merging two events costs event F1 more than any other metric here. Both PSDS
  profiles accept the merged detection, since 80% of it lies on the references.
- A missed event halves PSDS1 and PSDS2. One class drops to half its recall, and
  the spread between classes is subtracted from the mean.
- A wrong class takes both PSDS profiles to zero. PSDS2 also charges a
  cross-trigger on top of the false positive.

These results hold for this example only. Collars, segment length, thresholds
and the amount of audio all move the numbers.

## Setup

| Setting | Value |
| --- | --- |
| References | Two `siren` events (2 to 4 s, 5 to 7 s) and one `speech` event (10 to 14 s) |
| Clip | 20 s, within 600 s of audio split into 20 s recordings |
| Event F1 | 0.2 s collars, offset ratio 0.2, micro average |
| Segment metrics | 1 s segments, micro average |
| Frame F1 | 0.05 s frames, scores of 0 or 1, threshold 0.5, micro average |
| PSDS | PSDS1 and PSDS2 profiles on the same binary scores |

Binary scores give PSDS only one operating point besides the trivial ones. With
real score curves it integrates over many; see [PSDS](metrics/psds.md).

## Per-metric detail

| Metric | Page |
| --- | --- |
| Collars and matching | [Event F1](metrics/event_f1.md) |
| Segments and S/D/I | [Segment metrics](metrics/segment_f1.md) |
| Thresholds and ranking | [Frame labels](metrics/frame_binary.md) |
| Late score curves | [Frame events](metrics/frame_events.md) |
| Intersection criteria | [PSDS](metrics/psds.md) |
| Choice of post-processing | [piPSDS](metrics/pipsds.md) |
| Confidence | [Brier score](metrics/brier.md) |
| Alert delay | [Streaming protocol](streaming-protocol.md) |
