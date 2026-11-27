use sedmetrics_core::{
    Averaging, Event, Recording, SegmentConfig, ValidationError, segment_metrics,
};

fn event(recording_id: u32, class_id: u32, onset: f64, offset: f64) -> Event {
    Event {
        recording_id,
        class_id,
        onset,
        offset,
    }
}

fn config(segment_length: f64) -> SegmentConfig {
    SegmentConfig {
        segment_length,
        average: Averaging::Micro,
    }
}

fn recordings(ids: &[u32], duration: f64) -> Vec<Recording> {
    ids.iter()
        .map(|recording_id| Recording {
            recording_id: *recording_id,
            duration,
        })
        .collect()
}

#[test]
fn hand_computed_segment_metrics() {
    let references = [
        event(0, 0, 0.2, 2.1),
        event(0, 0, 5.0, 5.5),
        event(0, 1, 3.0, 4.0),
    ];
    let predictions = [
        event(0, 0, 0.5, 1.5),
        event(0, 0, 5.2, 5.4),
        event(0, 1, 3.5, 4.2),
    ];
    let durations = recordings(&[0], 10.0);

    let result = segment_metrics(&references, &predictions, &config(1.0), Some(&durations))
        .expect("fixture is valid");

    assert_eq!(result.n_true_positive, 4);
    assert_eq!(result.n_false_positive, 1);
    assert_eq!(result.n_false_negative, 1);
    assert_eq!(result.n_reference, 5);
    assert_eq!(result.precision.unwrap(), 4.0 / 5.0);
    assert_eq!(result.recall.unwrap(), 4.0 / 5.0);
    assert_eq!(result.f1.unwrap(), 4.0 / 5.0);

    assert_eq!(result.n_substitutions, 0);
    assert_eq!(result.n_deletions, 1);
    assert_eq!(result.n_insertions, 1);
    assert_eq!(result.error_rate.unwrap(), 2.0 / 5.0);
    assert_eq!(result.n_segments, 10);

    let class_zero = &result.classes[0];
    assert_eq!(class_zero.n_true_positive, 3);
    assert_eq!(class_zero.n_false_negative, 1);
    assert_eq!(class_zero.precision, Some(1.0));
    assert_eq!(class_zero.recall, Some(0.75));
}

#[test]
fn cross_class_activity_in_the_same_segment_is_a_substitution() {
    let references = [
        event(0, 0, 0.2, 2.1),
        event(0, 0, 5.0, 5.5),
        event(0, 0, 7.1, 7.9),
    ];
    let predictions = [
        event(0, 0, 0.5, 1.5),
        event(0, 0, 5.2, 5.4),
        event(0, 1, 7.2, 7.8),
        event(0, 1, 8.2, 8.8),
    ];
    let durations = recordings(&[0], 10.0);

    let result = segment_metrics(&references, &predictions, &config(1.0), Some(&durations))
        .expect("fixture is valid");

    // Segment 7 has a reference class 0 and a predicted class 1: one
    // substitution. Segment 2 is reference-only, segment 8 predicted-only.
    assert_eq!(result.n_substitutions, 1);
    assert_eq!(result.n_deletions, 1);
    assert_eq!(result.n_insertions, 1);
    assert_eq!(result.n_reference, 5);
    assert_eq!(result.n_predicted, 5);
    assert_eq!(result.error_rate.unwrap(), 3.0 / 5.0);

    // A substitution contributes one segment-level substitution but two
    // class-level errors (one FP and one FN), so FP + FN = 2 S + D + I.
    assert_eq!(
        result.n_false_positive + result.n_false_negative,
        2 * result.n_substitutions + result.n_deletions + result.n_insertions
    );
}

#[test]
fn segment_boundaries_are_half_open() {
    // [1.0, 2.0) activates exactly segment 1; a shared endpoint does not leak.
    let references = [event(0, 0, 1.0, 2.0), event(0, 0, 4.0, 5.0)];
    let predictions = [event(0, 0, 1.0, 2.0), event(0, 0, 4.999, 5.0)];
    let durations = recordings(&[0], 10.0);

    let result = segment_metrics(&references, &predictions, &config(1.0), Some(&durations))
        .expect("fixture is valid");

    // Segment 1: exact match. Segment 4: [4.999, 5.0) is ceil(5.0) = 5, so it
    // activates segment 4 only.
    assert_eq!(result.n_true_positive, 2);
    assert_eq!(result.n_false_positive, 0);
    assert_eq!(result.n_false_negative, 0);
}

#[test]
fn any_overlap_activates_a_segment() {
    let references = [
        event(0, 0, 0.0, 0.1),
        event(0, 0, 3.9, 4.1),
        event(0, 0, 6.0, 6.000_001),
    ];
    let durations = recordings(&[0], 10.0);

    let result = segment_metrics(&references, &[], &config(1.0), Some(&durations))
        .expect("fixture is valid");

    // 0.1 s in segment 0, a straddling event in segments 3 and 4, and a tiny
    // event in segment 6.
    assert_eq!(result.n_reference, 4);
    assert_eq!(result.n_false_negative, 4);
}

#[test]
fn durations_clamp_activity_past_the_end_of_the_recording() {
    // The event itself is rejected when durations are supplied.
    let durations = recordings(&[0], 10.0);
    let beyond = [event(0, 0, 9.5, 12.0)];
    let error = segment_metrics(&beyond, &[], &config(1.0), Some(&durations)).unwrap_err();
    assert!(matches!(error, ValidationError::OutsideRecording { .. }));

    // Without durations the evaluated length follows the data.
    let result = segment_metrics(&beyond, &[], &config(1.0), None).expect("no duration check");
    assert_eq!(result.n_segments, 12);
    assert_eq!(result.n_reference, 3);
}

#[test]
fn empty_inputs_have_undefined_ratios() {
    let result = segment_metrics(&[], &[], &config(1.0), None).expect("empty is valid");
    assert_eq!(result.f1, None);
    assert_eq!(result.error_rate, None);
    assert_eq!(result.n_segments, 0);
    assert_eq!(result.n_classes, 0);

    let no_predictions =
        segment_metrics(&[event(0, 0, 0.0, 1.0)], &[], &config(1.0), None).expect("valid");
    assert_eq!(no_predictions.precision, None);
    assert_eq!(no_predictions.recall, Some(0.0));
    assert_eq!(no_predictions.f1, Some(0.0));
    assert_eq!(no_predictions.error_rate, Some(1.0));
}

#[test]
fn macro_averaging_is_the_mean_of_class_scores() {
    let references = [event(0, 0, 0.0, 3.0), event(0, 1, 4.0, 5.0)];
    let predictions = [
        event(0, 0, 0.0, 3.0),
        event(0, 1, 4.0, 5.0),
        event(0, 1, 7.0, 8.0),
    ];
    let mut config = config(1.0);
    config.average = Averaging::Macro;

    let result = segment_metrics(&references, &predictions, &config, None).expect("valid");

    // Class 0: F1 = 1. Class 1: precision 0.5, recall 1, F1 = 2/3.
    assert_eq!(result.classes[0].f1, Some(1.0));
    assert_eq!(result.classes[1].f1.unwrap(), 2.0 / 3.0);
    assert_eq!(result.f1.unwrap(), (1.0 + 2.0 / 3.0) / 2.0);
}

#[test]
fn invalid_segment_length_is_rejected() {
    for value in [0.0, -1.0, f64::NAN, f64::INFINITY] {
        let error = segment_metrics(&[], &[], &config(value), None).unwrap_err();
        assert!(matches!(
            error,
            ValidationError::InvalidParameter {
                field: "segment_length",
                ..
            }
        ));
    }
}

#[test]
fn class_totals_pool_over_recordings() {
    let references = [event(0, 0, 0.0, 1.0), event(1, 0, 0.0, 1.0)];
    let predictions = [event(0, 0, 0.0, 1.0), event(1, 0, 0.0, 1.0)];
    let durations = recordings(&[0, 1], 2.0);

    let result =
        segment_metrics(&references, &predictions, &config(1.0), Some(&durations)).expect("valid");

    assert_eq!(result.n_classes, 1);
    assert_eq!(result.n_true_positive, 2);
    assert_eq!(result.n_segments, 4);
    assert_eq!(result.f1, Some(1.0));
}
