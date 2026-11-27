---
title: "Streaming sound event detection metrics"
description: "Experimental protocol for alert timing: matching window, deadline recall, AUDR, censoring and false alerts per hour."
faq:
  - q: "Does an alert before the onset count as an early detection?"
    a: "No. It is never eligible, and it counts as a false alert."
  - q: "What is AUDR?"
    a: "The area under deadline recall from 0 to a horizon H, divided by H."
  - q: "How are events near the end of a recording treated?"
    a: "If the matching window runs past the end, the event is censored: it is counted separately and is never a miss."
---

# Streaming evaluation protocol (experimental CREATE baseline)

Streaming metrics measure when a detector's decision became available. This experimental protocol matches each alert to at most one event and reports recall by deadline, the area under that curve (AUDR) and false alerts per hour.

Status: experimental implementation, version `streaming_create/1`.
This is a research protocol and has not been independently validated on real
detector traces. Only immutable CREATE records are accepted; lifecycle-aware
evaluation is not implemented.

Motivation: every metric `M(G, P)` that depends only on references `G` and final
predictions `P` assigns the same value to two systems with identical `P` but
different emission histories. Streaming metrics measure *when* a
decision became available, and complement offline localization metrics.
Prior early-detection work such as [SEED](https://arxiv.org/abs/2202.02441)
reports detection delay and F1 under its own eligibility and early-prediction
rules. The protocol here makes different choices, including no pre-onset credit;
it is not claimed to reproduce SEED or establish novelty.

## What do streaming metrics penalise?

Streaming metrics charge for the time between an event starting and the alert
arriving. The grey band is the matching window. The black triangle is a matched
alert, the red one a false alert.

<div class="pen" data-figure="streaming"></div>

| Mistake | Effect |
| --- | --- |
| Later alert inside the window | Recall at earlier deadlines falls; AUDR falls linearly with the delay, down to zero at the horizon |
| Alert before the onset | A false alert, and the event stays unmatched |
| Alert after the window | A false alert and a miss |
| Repeated alert for one event | Every extra one is a false alert |
| Event too close to the end of the recording | Censored: left out of recall, counted separately |

## Usage

```python
from sedmetrics import SEDMetrics

result = SEDMetrics.eval(
    references=[(0, 0, 0.0, 0.5)], mode="streaming", recordings={0: 10.0},
    alerts=[(0, 1, 0, 0.1, 0.1, 0.1)],
    class_ids=[0], matching_window=1.0, deadlines=[0.25, 0.5], horizon=1.0, clock="simulated",
)
print(result["deadline_recall"], result["audr"], result["false_alerts_per_hour"])
```

An alert is `(recording_id, alert_id, class_id, emitted_at,
audio_available_until, latest_audio_used)`; the last value may be `None`.

## 1. Entities and clocks

- All times are seconds, `f64`, on one recording's time axis.
- `estimated_onset` / `estimated_offset`: the system's retrospective estimate of
  the event. These are not decision times.
- `emitted_at`: the time at which a downstream consumer receives the decision.
  This is the only time used for latency.
- `audio_available_until` and `latest_audio_used`: how much audio existed at
  emission and how much the system actually consumed. Availability must include
  buffering, preprocessing, look-ahead, inference and post-processing.
- Simulated algorithmic availability is allowed for replay studies, but must be
  labelled as simulated. Measured latency may not be claimed from simulated
  timestamps.
- Validation: `latest_audio_used <= audio_available_until <= emitted_at`,
  monotone `emitted_at` per recording, unique `(recording_id, alert_id)`, and
  all times inside the recording. This CREATE-only API does not accept or
  validate lifecycle records or sequence ids. A clock label is required but
  self-reported timestamps do not prove causality.
- An explicit nonempty class vocabulary is required; unknown reference and alert
  classes are rejected, including in recordings without reference events.

## 2. What is scored

- Immutable CREATE alerts only. `Update`, `Cancel` and `Close` are not
  accepted or scored; retaining and validating lifecycle logs is future work.
- Every CREATE alert is matched at most once and every reference event at most
  once.
- Unmatched CREATE alerts, including duplicates of an already matched alert, are
  false alerts.
- A valid but late alert (inside the eligibility window, later than a deadline)
  is a matched alert with a large delay; it is not an unmatched alert.

Rationale: crediting an `Update` would let a system "emit" unlimited refinements
and hide the fact that the first decision was late.

## 3. Eligibility window and matching

For a reference event with onset `g_on` and offset `g_off`:

With onset $g$, emission time $t$ and matching window $W$, an alert is eligible
when

$$
g \le t \le g + W
$$

!!! deviation "Current behaviour: the window edge in floating point"

    The code tests $t - g \le W$, which rounds differently. With onset `1.0`,
    window `0.3` and an alert at `1.3`, the difference is
    `0.30000000000000004`, so the alert counts as false. Deadlines are
    compared the same way. Use binary-exact times at the edge.

- `matching_window` is a required configuration parameter and must be reported.
  There is no silent default in the API; analysis notebooks may use 2.0 s as a
  documented choice.
- Pre-onset alerts are never eligible. Negative delays are never clamped to
  zero: an early alert is a false alert, not a perfect detection.
- Post-offset alerts are eligible only when they fall inside the window; the
  window is event-relative, not a fixed multiple of the duration.
- Eligibility requires the same recording and the same class.

Assignment per `(recording, class)` group:

1. Build the bipartite graph of eligible reference/alert pairs.
2. Choose a maximum-cardinality matching.
3. Among maximum-cardinality matchings, minimise the total delay:

    $$
    \min_{M} \sum_{(i,j) \in M} (t_j - g_i)
    $$

4. Resolve remaining ties deterministically by stable input order and dynamic
   programming traversal. This is not a guarantee of lexicographically minimal pairs.

Report the policy with every result. This assignment is fixed before deadline
curves are computed, so `DAR(t)` is monotone in `t` and `AUDR` is monotone in
the delays. It does not maximise recall at every individual deadline; a
deadline-specific rematching variant would be a different, separately named
metric if added.

## 4. Metrics

With $N$ the number of eligible references in the fully observed cohort and
$d_i \ge 0$ the delay of matched reference $i$ ($d_i = +\infty$ for a fully
observed miss), deadline recall at an explicit deadline $t$ is

$$
\mathrm{DAR}(t) = \frac{\#\{\, i : d_i \le t \,\}}{N}
$$

and its normalised area up to a horizon $H > 0$ is

$$
\mathrm{AUDR}(H) = \frac{1}{H} \int_0^H \mathrm{DAR}(t)\,dt
= \frac{1}{N} \sum_{i=1}^{N} \max\Bigl(0,\; 1 - \cost{\frac{d_i}{H}}\Bigr)
$$

With $A$ CREATE alerts, $\lvert M \rvert$ matched pairs and $T$ seconds of
observed audio, the false-alert rate per hour is

$$
\mathrm{FA/h} = \frac{\cost{A - \lvert M \rvert}}{T / 3600}
$$

Matched-delay statistics (mean, median, P90, P95) are reported together with
the matched count and recall; never rank systems by delay conditional on
detection alone.

`TW-F1` and the deadline/false-alarm surface remain research items; they are not
part of this baseline. A deadline/false-alarm envelope may only include
configurations that correspond to realizable causal policies and their own alert
logs.

## 5. Censoring and observation

- Observation covers the entire supplied recording duration, with no tail and no
  early termination in this version. The caller must ensure this is true.
- A reference whose eligibility window is not fully observed (it extends past the
  observation end) is censored: it is excluded from the fully observed
  cohort, counted separately, and never counted as a confirmed miss.
- Matching includes all references, including censored references, before the
  observed cohort is selected. A censored reference can consume an alert that
  could match an observed reference; this is a deliberate limitation of this
  fixed global assignment. Matched censored alerts are not false alerts, and
  censored references contribute neither credit nor misses to cohort recall.
  Both their count and their matched count are reported.
- A reference with a fully observed window and no matched alert is a miss.
- Observation ends at the clip boundary; no tail time is added.

Reports must include `n_reference_total`, `n_reference_censored`,
`n_reference_observed`, `matching_window`, deadlines and horizon.

!!! deviation "Current behaviour: field names"

    The result uses `n_reference`, `n_censored` and `n_observed` for those three
    counts. `matching_window`, `deadlines` and `horizon` appear as named.

## 6. Exposure

False alerts per hour uses the duration of all evaluated recordings,
including recordings with no reference events for the class. The rate is global
by default; class-wise counts are reported but the headline rate is not
class-wise. Zero exposure makes `FA/h` undefined (`None`), never zero.

!!! deviation "Current behaviour: no class-wise counts"

    The result holds global counts only. For per-class figures, evaluate one
    class at a time.

## 7. Consequences for the implementation

- The CREATE log is validated before evaluation; malformed inputs raise.
- The matcher uses a dynamic program per recording and class. With a common
  fixed window, if two eligible pairs cross in onset/emission order, swapping
  their alerts preserves eligibility, cardinality and total delay. Thus an
  optimal non-crossing matching exists. Each group uses $O(RA)$ time and memory;
  ties follow stable traversal order. This argument depends on the common window
  and would not automatically hold for event-specific windows.
- Everything except the alert log is deterministic: no wall clock, no random
  sampling, no thread-order dependence.
- Every result carries the protocol version, the configuration and the cohort
  counts so that two reports can be compared without guessing.
