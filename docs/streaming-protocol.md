# Streaming evaluation protocol (decided baseline)

Status: **protocol fixed, implementation not started.** The metric family is
still provisional in the sense that independent validation has not been done; the
rules below are the contract any implementation and any report must follow.

Motivation: every metric `M(G, P)` that depends only on references `G` and final
predictions `P` assigns the same value to two systems with identical `P` but
different emission histories. Streaming metrics exist to measure *when* a
decision became available, not to replace offline localization metrics.

## 1. Entities and clocks

- All times are seconds, `f64`, on one recording's time axis.
- `estimated_onset` / `estimated_offset`: the system's retrospective estimate of
  the event. These are **not** decision times.
- `emitted_at`: the time at which a downstream consumer receives the decision.
  This is the only time used for latency.
- `audio_available_until` and `latest_audio_used`: how much audio existed at
  emission and how much the system actually consumed. Availability must include
  buffering, preprocessing, look-ahead, inference and post-processing.
- Simulated algorithmic availability is allowed for replay studies, but must be
  labelled as simulated. Measured latency may not be claimed from simulated
  timestamps.
- Validation: causal (`latest_audio_used <= audio_available_until`), monotone
  `emitted_at` per recording, consistent recording/class identity, legal action
  transitions, unique `(alert_id, sequence_id)`.

## 2. What is scored

- **Immutable CREATE alerts only.** `Update`, `Cancel` and `Close` are validated
  for legality and kept for auditing, but contribute no credit.
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

```
eligible alert:  g_on <= emitted_at <= g_on + matching_window
```

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
2. Choose a **maximum-cardinality** matching.
3. Among maximum-cardinality matchings, minimise the **total delay**
   `Σ (emitted_at - g_on)`.
4. Break remaining ties deterministically by reference index, then alert index.

Report the policy with every result. This assignment is fixed before deadline
curves are computed, so `DAR(t)` is monotone in `t` and `AUDR` is monotone in
the delays. It does **not** maximise recall at every individual deadline; a
deadline-specific rematching variant would be a different, separately named
metric if added.

## 4. Metrics

With `N` the number of eligible references in the fully observed cohort, `A` the
number of CREATE alerts, `M` matched pairs and `d_i >= 0` the delay of matched
reference `i` (`d_i = +inf` for a fully observed miss):

- `DAR(t) = #{i : d_i <= t} / N` at explicit deadlines.
- `AUDR(H) = (1/H) ∫_0^H DAR(t) dt = Σ_i max(0, 1 - d_i/H) / N`, `H > 0`.
- Matched-delay statistics: mean, median, P90, P95 **together with** the matched
  count and recall; never rank systems by delay conditional on detection alone.
- `FA/h = unmatched CREATE alerts / observed audio hours`.

`TW-F1` and the deadline–false-alarm surface remain research items; they are not
part of this baseline. A deadline–false-alarm envelope may only include
configurations that correspond to realizable causal policies and their own alert
logs.

## 5. Censoring and observation

- The observation end for a recording is `min(last audio available, window end)`.
- A reference whose eligibility window is not fully observed (it extends past the
  observation end) is **censored**: it is excluded from the fully observed
  cohort, counted separately, and never counted as a confirmed miss.
- A reference with a fully observed window and no matched alert is a miss.
- Observation ends at the clip boundary; no tail time is added.

Reports must include `n_reference_total`, `n_reference_censored`,
`n_reference_observed`, `matching_window`, deadlines and horizon.

## 6. Exposure

False alerts per hour uses the duration of **all evaluated recordings**,
including recordings with no reference events for the class. The rate is global
by default; class-wise counts are reported but the headline rate is not
class-wise. Zero exposure makes `FA/h` undefined (`None`), never zero.

## 7. Consequences for the implementation

- The alert log is a Rust domain type validated before evaluation; malformed
  logs raise, they are never repaired.
- The matcher needs a maximum-cardinality + minimum-total-delay assignment over
  a bipartite graph whose edges are sparse (one window per reference), so a
  min-cost max-flow formulation is acceptable; the deterministic tie-break must
  be part of the test fixtures.
- Everything except the alert log is deterministic: no wall clock, no random
  sampling, no thread-order dependence.
- Every result carries the protocol version, the configuration and the cohort
  counts so that two reports can be compared without guessing.
