---
title: "SEDMetrics Python and Rust API"
description: "Reference for SEDMetrics.eval, the lower-level Python functions and the sedmetrics-core Rust crate for sound event evaluation."
---

# SEDMetrics API reference

SEDMetrics has two interfaces over the same Rust core: a Python package,
`sedmetrics`, and a Rust crate, `sedmetrics-core`. Choose your language.

=== ":logos-python: Python"

    ## Install the Python package { #python }

    ```bash
    python -m pip install sedmetrics
    ```

    ```python
    from sedmetrics import SEDMetrics

    result = SEDMetrics.eval(
        references=[(0, 0, 2.0, 5.0)],
        predictions=[(0, 0, 2.1, 5.0)],
    )
    print(result.f1, result.n_correct)  # 1.0 1
    ```

    ## Python entry point

    ```python
    SEDMetrics.eval(references, predictions=None, *, mode=None, metric=None,
                    metrics=None, recordings=None, scores=None, alerts=None,
                    metric_options=None, **options)
    ```

    | Selection | Required input | Result |
    | --- | --- | --- |
    | Default or `metric="event_f1"` | Reference and predicted events | Event F1 result |
    | `metric="segment_f1"` | Events and recording durations | Segment result |
    | `metric="psds"` | Events, durations, score tracks | PSDS result |
    | `metric="pipsds"` | Events, durations, named processed score tracks | piPSDS envelope |
    | `mode="frame"` | Aligned labels and scores, or events, durations and score tracks | Frame statistics |
    | `mode="probability"` | Aligned targets and probabilities | Brier result |
    | `mode="streaming"` | Events, durations, class IDs, and CREATE alerts | Experimental streaming statistics |

    The first two arguments change meaning with the mode. In probability mode,
    `references` holds the targets and `scores=` the probabilities. In aligned
    frame mode, `references` holds Boolean labels and `scores=` the frame scores.
    Streaming mode takes the alerts through `alerts=`.

    For event metrics, `metrics=[...]` returns a dictionary of results and
    `metric_options` maps metric names to option dictionaries. In aligned frame
    mode, `metrics` selects scalar fields while retaining counts and
    configuration. Event-based frame mode returns all its classwise and aggregate
    metrics.

    ## Python functions

    | Function in `sedmetrics` | Evaluates | Arguments |
    | --- | --- | --- |
    | `event.f1` | Collar-based event F1 | `references`, `predictions` |
    | `segment.f1` | Segment F1 and error rate | `references`, `predictions` |
    | `frame.evaluate` | Aligned binary labels and scores | `labels`, `scores`, `threshold` |
    | `frame.events` | Score tracks against events, by class | `references`, `scores`, `recordings`, `threshold` |
    | `frame.brier` | Aligned probabilities and soft targets | `targets`, `probabilities` |
    | `psds.psds` | PSDS from score tracks | `references`, `scores`, `recordings` |
    | `psds.pipsds` | piPSDS from named processed tracks | `references`, `processed_scores`, `recordings` |
    | `experimental.streaming.evaluate` | CREATE alert logs | `references`, `alerts`, `recordings`, `class_ids`, `matching_window`, `deadlines`, `horizon`, `clock` |
    | `report.evaluate` | A JSON-compatible report of event and segment metrics, plus PSDS when `scores=` is supplied | `dataset`, `predictions` |
    | `report.write_report` | Writes that report to disk | `report`, `path` |
    | `adapters.load_urban_sed` | Loads URBAN-SED references | `root` |
    | `adapters.load_audioset_strong` | Loads AudioSet Strong references | `root` |

    Each [metric specification](choosing-metrics.md) lists the optional
    parameters, tie handling, aggregation and undefined values.

    ## Python results and errors

    Event, segment, PSDS and piPSDS calls return result objects with a
    `to_dict()` method. Frame, Brier and streaming calls return dictionaries.
    Undefined values are `None`. Invalid input raises
    `sedmetrics.ValidationError`, a subclass of `ValueError`, or a plain
    `ValueError` for an argument that does not fit the selected mode.

=== ":logos-rust: Rust"

    ## Add the Rust crate { #rust }

    ```toml
    [dependencies]
    sedmetrics-core = "0.1.0"
    ```

    The crate has no third-party dependencies, does no file input or output and
    does not depend on Python.

    ## Rust example

    ```rust
    use sedmetrics_core::{
        Event, EventF1Config, PsdsConfig, Recording, ScoreTrack, ValidationError, event_f1, psds,
    };

    fn main() -> Result<(), ValidationError> {
        let references = [Event { recording_id: 0, class_id: 0, onset: 2.0, offset: 5.0 }];
        let predictions = [Event { recording_id: 0, class_id: 0, onset: 2.1, offset: 5.0 }];
        let recordings = [Recording { recording_id: 0, duration: 10.0 }];

        let events = event_f1(
            &references,
            &predictions,
            &EventF1Config::default(),
            Some(&recordings),
        )?;
        println!("event F1: {:?}", events.f1); // event F1: Some(1.0)

        // Scores are row-major: one row per frame, one column per class id.
        let tracks = [ScoreTrack {
            recording_id: 0,
            class_ids: vec![0],
            boundaries: vec![0.0, 2.0, 5.0, 10.0],
            scores: vec![0.0, 0.9, 0.0],
        }];
        let psds1 = psds(&references, &tracks, &recordings, &PsdsConfig::default())?;
        let psds2 = psds(&references, &tracks, &recordings, &PsdsConfig::psds2())?;
        println!("PSDS1: {:.3}, PSDS2: {:.3}", psds1.psds, psds2.psds);
        // PSDS1: 1.000, PSDS2: 1.000
        Ok(())
    }
    ```

    ## Rust functions

    | Function | Arguments | Returns |
    | --- | --- | --- |
    | `event_f1` | `references`, `predictions`, `config`, `recordings` | `Result<EventF1Result, ValidationError>` |
    | `segment_metrics` | `references`, `predictions`, `config`, `recordings` | `Result<SegmentResult, ValidationError>` |
    | `psds` | `references`, `tracks`, `recordings`, `config` | `Result<PsdsResult, ValidationError>` |
    | `merge_postprocessings` (piPSDS) | `results` | `Result<PsdsResult, &'static str>` |
    | `labels_from_events` | `references`, `recording`, `class_id`, `boundaries` | `Result<Vec<bool>, String>` |
    | `frame_metrics` | `labels`, `scores`, `weights`, `threshold` | `Result<FrameResult, &'static str>` |
    | `brier` | `targets`, `probabilities`, `weights` | `Result<BrierResult, &'static str>` |
    | `evaluate_streaming` | `references`, `alerts`, `recordings`, `class_ids`, `window`, `deadlines`, `horizon` | `Result<StreamingResult, String>` |
    | `maximum_matching` | `references`, `predictions`, `config` | `Vec<(usize, usize)>` |

    `event_f1` and `segment_metrics` take `recordings` as an
    `Option<&[Recording]>`.

    ## Rust types

    | Type | Holds |
    | --- | --- |
    | `Event` | `recording_id`, `class_id`, `onset`, `offset`, in seconds |
    | `Recording` | `recording_id` and `duration` |
    | `ScoreTrack` | Frame boundaries and row-major `f32` scores for one recording |
    | `CreateAlert` | One streaming alert with its emission and audio times |
    | `CollarConfig`, `EventF1Config` | Collars and averaging for event F1 |
    | `SegmentConfig` | Segment length and averaging |
    | `PsdsConfig` | PSDS criteria; the default is PSDS1 and `psds2()` is PSDS2 |
    | `Averaging`, `TimeUnit` | Micro or macro; second, minute or hour |
    | `ValidationError` | The rejected input and the reason |
