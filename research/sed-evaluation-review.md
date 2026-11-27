# Sound event detection evaluation: research review

Review date: 2026-11-27. Scope: polyphonic temporal SED, with emphasis on
established protocols, their blind spots, and evaluation of actual alerts.
This is a focused literature review, not an exhaustive novelty search.

## What the metric families measure

| Family | Unit and benefit | Main limitation | Project status |
| --- | --- | --- | --- |
| Frame classification | Activity on explicit score intervals; useful for fine temporal activity and ranking | Depends on grid, label mapping, weighting and class prevalence; does not score connected events | Not implemented |
| Segment F1 and S/D/I error rate | Class activity within fixed segments, with segment-wise substitutions | Resolution and origin affect results; long events contribute to many segments, and fragmentation is obscured | Implemented; selected `sed_eval` parity |
| Collar event F1 | One-to-one event counts with tolerated onset/offset errors | Sensitivity depends on event duration and annotation convention; fragmentation can be penalized heavily | Implemented; selected `sed_eval` parity |
| Intersection and PSDS | Overlap criteria and effective false-positive-rate curves over operating points | Depends on DTC/GTC/CTTC, class support, exposure and post-processing; does not measure actual decision time | Score-based PSDS implemented; selected `sed_scores_eval` parity |
| piPSDS | Envelope over thresholds and post-processing configurations | An envelope can combine different configurations and is not one deployable system | Not implemented |
| Early/online evaluation | Alert availability, delay and false-alert exposure | Requires trustworthy clock metadata, a matching and censoring protocol, and real alert logs | Provisional protocol only |
| Soft labels and calibration | Agreement with uncertainty or probabilistic references | Depends on annotation generation, calibration target, and weighting; is not interchangeable with event detection | Not implemented |

Mesaros et al. define segment and event measures and emphasize that metric
choice depends on the application ([2016 paper](https://doi.org/10.3390/app6060162)).
Ferroni et al. investigate how collars, segments and intersections affect SED
comparisons ([2021 paper](https://arxiv.org/abs/2010.13648)). Bilen et al.
define PSDS, DTC, GTC and cross-triggers ([2020 paper](https://arxiv.org/abs/1910.08440)).

## Score sweeps and operating policies

Ebbers et al. show that a sampled threshold sweep may underestimate PSDS and
describe an efficient change-point algorithm for evaluating all thresholds
([2022 paper](https://arxiv.org/abs/2201.13148)). SEDMetrics currently enumerates
distinct finite scores directly; it is not the paper's incremental algorithm.
This is exact over those inputs and the implemented comparison semantics, not
evidence of complete compatibility or speed. Compare intermediate statistics
against an exhaustive independent oracle before optimization.

The piPSDS paper extends the envelope across post-processings as well as
thresholds ([2023 paper](https://arxiv.org/html/2306.15440)). Different points
may use different configurations. An envelope is useful for comparison but is
not itself a fixed deployable policy. Causal claims also require recording any
look-ahead and actual processing time.

## Decision availability and research gap

The SEED paper explicitly evaluates early detection and conditional detection
delay, including its own early-prediction tolerance and delay convention
([SEED](https://arxiv.org/abs/2202.02441)). It is prior art, not proof that a
particular SEDMetrics alert-log protocol is novel. Final predicted intervals
alone cannot distinguish systems that emit the same final boundaries at different
times. That information limitation follows directly from their inputs; it is not
a defect in offline localization metrics.

Proposed complementary outputs are fixed-assignment deadline recall, normalized
area under its curve, matched delay quantiles, and unmatched CREATE alerts per
hour of observed audio. Report them together with offline metrics. Before code,
resolve how censored references interact with matching and false alerts, define
the observation and clock model, and validate against a simple independent oracle.
The proposal is experimental and its estimates depend on trustworthy alert logs.

## Soft labels and low false-positive regimes

The [DCASE 2024 Task 4 protocol](https://dcase.community/challenge2024/task-sound-event-detection-with-heterogeneous-training-dataset-and-potentially-missing-labels)
uses MAESTRO soft annotations but specifies a hard-label evaluation convention
for its 1-second segment metrics, including macro partial AUC at FPR 0.1; its
DESED component uses PSDS. Thus a dataset containing soft labels does not imply
that a reported benchmark metric directly evaluates soft targets. Proper scores
such as Brier score are a possible additional view only for explicitly defined
probability targets, not a replacement for the challenge protocol.

## Priorities for SEDMetrics

1. Specify and implement binary frame precision/recall/F1 with explicit class
   vocabulary, frame-to-reference alignment, frame versus duration weighting,
   thresholds, ties and undefined values. Add AP/AUROC separately with a pinned
   classification oracle and explicit missing-class behavior.
2. Establish exhaustive small-case PSDS and cross-trigger component oracles,
   full score coverage, and pinned, reproducible parity environments.
3. Resolve the alert cohort/censoring contract and implement a small experimental
   CREATE-alert baseline with hand examples and an independent Python oracle.
4. Add piPSDS and calibrated/soft-label measures only with individual protocol
   specifications and reference checks; distinguish hypothetical policy
   envelopes from operational evaluation.
5. Quantify uncertainty at recording/scene level and report class and duration
   strata; do not infer real-time latency from retrospective event boundaries.

Open questions: which label-to-frame policy and absent-class convention should
be public defaults, and which matching/censoring policy should govern alerts?
These choices can change reported results and need explicit specifications.
