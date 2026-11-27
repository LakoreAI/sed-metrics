---
title: "Which sound event detection metric to use"
description: "Pick event F1, segment metrics, frame metrics, PSDS, piPSDS, Brier score or streaming metrics by the decision you need to evaluate."
faq:
  - q: "Can I compare event F1 with PSDS?"
    a: "Not as numbers. They take different inputs and charge for different mistakes. Compare systems under one metric with the same settings."
  - q: "Which metrics need score tracks instead of events?"
    a: "Frame metrics on score tracks, PSDS and piPSDS."
---

# Choosing sound event detection metrics

Use event F1 when event boundaries matter and segment metrics when activity per time block matters. With score tracks, use frame metrics or PSDS. Use the Brier score for probabilities and the experimental streaming protocol for alert timing.

Choose metrics based on the decision you need to evaluate. A score track, a
list of final events, and an alert log contain different information.

| Question | Start with | Important setting |
| --- | --- | --- |
| Are estimated event boundaries close to the annotations? | [Event F1](metrics/event_f1.md) | Onset and offset collars |
| Is the class active in a fixed time block? | [Segment metrics](metrics/segment_f1.md) | Segment length and origin |
| How well do scores rank activity on a known grid? | [Frame metrics](metrics/frame_events.md) | Label mapping and frame weighting |
| How does detection vary across thresholds? | [PSDS](metrics/psds.md) | Intersection criteria and false-positive range |
| How does an envelope vary across supplied processing choices? | [piPSDS](metrics/pipsds.md) | The set of processed tracks |
| Are predicted probabilities close to target probabilities? | [Brier score](metrics/brier.md) | Meaning of soft targets |
| When did an alert arrive? | [Streaming metrics](streaming-protocol.md) | Clock, matching window, and observation period |

[How metrics penalise mistakes](penalties.md) scores the same detector outputs
under several of these side by side.

Report the configuration with the score. A piPSDS envelope can combine
different post-processing configurations and is not the score of a single
deployed policy. An offline event onset is not an alert emission time.
