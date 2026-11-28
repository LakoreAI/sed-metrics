use sedmetrics::matching::{CollarConfig, maximum_matching};
use sedmetrics::{
    Averaging, Event, EventF1Config, EventF1Result, Recording, ValidationError, event_f1,
};

fn event(recording_id: u32, class_id: u32, onset: f64, offset: f64) -> Event {
    Event {
        recording_id,
        class_id,
        onset,
        offset,
    }
}

fn config(onset_collar: f64, offset_collar: f64, offset_ratio: f64) -> EventF1Config {
    EventF1Config {
        collar: CollarConfig {
            onset_collar,
            offset_collar,
            offset_ratio,
            evaluate_offset: true,
        },
        average: Averaging::Micro,
    }
}

fn run(references: &[Event], predictions: &[Event], config: &EventF1Config) -> EventF1Result {
    event_f1(references, predictions, config, None).expect("fixture should be valid")
}

fn assert_close(actual: Option<f64>, expected: f64, context: &str) {
    let actual = actual.unwrap_or_else(|| panic!("{context}: expected {expected}, got None"));
    assert!(
        (actual - expected).abs() < 1e-12,
        "{context}: expected {expected}, got {actual}"
    );
}

#[test]
fn counts_and_micro_ratios_follow_the_hand_computation() {
    let references = [
        event(0, 0, 0.0, 1.0),
        event(0, 0, 2.0, 3.0),
        event(0, 0, 4.0, 5.0),
    ];
    let predictions = [
        event(0, 0, 0.0, 1.0),
        event(0, 0, 2.0, 3.0),
        event(0, 0, 7.0, 8.0),
    ];

    let result = run(&references, &predictions, &config(0.2, 0.2, 0.2));

    assert_eq!(result.n_reference, 3);
    assert_eq!(result.n_predicted, 3);
    assert_eq!(result.n_correct, 2);
    assert_eq!(result.n_insertions, 1);
    assert_eq!(result.n_deletions, 1);
    assert_close(result.precision, 2.0 / 3.0, "precision");
    assert_close(result.recall, 2.0 / 3.0, "recall");
    assert_close(result.f1, 4.0 / 6.0, "f1");
    assert_close(result.mean_onset_error, 0.0, "mean onset error");
}

#[test]
fn collar_boundaries_are_inclusive_and_exact() {
    // Binary-exact values so that the boundary comparison itself is what is tested.
    let references = [event(0, 0, 1.0, 2.0)];
    let config = config(0.25, 0.25, 0.0);

    let at_boundary = [event(0, 0, 1.25, 2.25)];
    assert_eq!(run(&references, &at_boundary, &config).n_correct, 1);

    let just_past_onset = [event(0, 0, 1.25 + f64::EPSILON * 2.0, 2.25)];
    assert_eq!(run(&references, &just_past_onset, &config).n_correct, 0);

    let past_offset = [event(0, 0, 1.0, 2.5)];
    assert_eq!(run(&references, &past_offset, &config).n_correct, 0);
}

#[test]
fn offset_tolerance_uses_the_reference_duration_ratio() {
    // 25 % of a 10 s reference is 2.5 s, which dominates the 200 ms collar.
    let references = [event(0, 0, 0.0, 10.0)];
    let config = config(0.2, 0.2, 0.25);

    let at_boundary = [event(0, 0, 0.0, 12.5)];
    assert_eq!(run(&references, &at_boundary, &config).n_correct, 1);

    let past_boundary = [event(0, 0, 0.0, 13.0)];
    assert_eq!(run(&references, &past_boundary, &config).n_correct, 0);
}

#[test]
fn onset_only_protocol_ignores_offset_differences() {
    let references = [event(0, 0, 1.0, 2.0)];
    let mut config = config(0.2, 0.2, 0.2);
    config.collar.evaluate_offset = false;

    let predictions = [event(0, 0, 1.05, 9.0)];
    assert_eq!(run(&references, &predictions, &config).n_correct, 1);
}

#[test]
fn augmenting_paths_recover_a_second_match_that_greedy_assignment_loses() {
    // R1 can take P1 or P2; R2 can only take P1. A greedy pass gives R1 -> P1 and
    // leaves R2 unmatched, so a correct implementation must reassign R1 -> P2.
    let references = [event(0, 0, 0.0, 10.0), event(0, 0, 0.05, 8.05)];
    let predictions = [event(0, 0, 0.0, 8.0), event(0, 0, 0.0, 10.5)];
    let config = config(0.2, 0.2, 0.2);

    let result = run(&references, &predictions, &config);

    assert_eq!(result.n_correct, 2);
    assert_eq!(result.n_insertions, 0);
    assert_eq!(result.n_deletions, 0);
    assert_close(result.f1, 1.0, "f1");
}

#[test]
fn duplicate_predictions_do_not_add_matches() {
    let references = [event(0, 0, 1.0, 2.0)];
    let predictions = [event(0, 0, 1.0, 2.0), event(0, 0, 1.0, 2.0)];

    let result = run(&references, &predictions, &config(0.2, 0.2, 0.2));

    assert_eq!(result.n_correct, 1);
    assert_eq!(result.n_insertions, 1);
    assert_close(result.precision, 0.5, "precision");
    assert_close(result.recall, 1.0, "recall");
}

#[test]
fn results_are_invariant_to_input_permutation() {
    let references = [
        event(0, 0, 0.0, 1.0),
        event(1, 0, 0.5, 1.5),
        event(0, 1, 2.0, 2.5),
        event(1, 1, 3.0, 4.0),
    ];
    let predictions = [
        event(1, 1, 3.05, 4.02),
        event(0, 1, 2.4, 3.2),
        event(0, 0, 0.05, 1.1),
        event(0, 0, 9.0, 9.5),
    ];
    let config = config(0.2, 0.2, 0.2);

    let forward = run(&references, &predictions, &config);

    let mut reversed_references = references;
    reversed_references.reverse();
    let mut reversed_predictions = predictions;
    reversed_predictions.reverse();
    let reversed = run(&reversed_references, &reversed_predictions, &config);

    assert_eq!(forward.n_correct, reversed.n_correct);
    assert_eq!(forward.n_insertions, reversed.n_insertions);
    assert_eq!(forward.n_deletions, reversed.n_deletions);
    assert_eq!(forward.classes, reversed.classes);
}

#[test]
fn class_totals_pool_over_recordings() {
    let references = [
        event(0, 0, 0.0, 1.0),
        event(1, 0, 0.0, 1.0),
        event(1, 0, 5.0, 6.0),
    ];
    let predictions = [event(0, 0, 0.0, 1.0), event(1, 0, 5.0, 6.0)];

    let result = run(&references, &predictions, &config(0.2, 0.2, 0.2));

    assert_eq!(result.n_classes, 1);
    assert_eq!(result.classes[0].n_reference, 3);
    assert_eq!(result.classes[0].n_predicted, 2);
    assert_eq!(result.classes[0].n_correct, 2);
    assert_eq!(result.classes[0].n_deletions, 1);
}

#[test]
fn undefined_ratios_are_none_not_zero() {
    let nothing = run(&[], &[], &config(0.2, 0.2, 0.2));
    assert_eq!(nothing.precision, None);
    assert_eq!(nothing.recall, None);
    assert_eq!(nothing.f1, None);
    assert_eq!(nothing.n_classes, 0);

    let references_only = [event(0, 0, 0.0, 1.0)];
    let only_references = run(&references_only, &[], &config(0.2, 0.2, 0.2));
    assert_eq!(only_references.precision, None);
    assert_close(only_references.recall, 0.0, "recall");
    assert_close(only_references.f1, 0.0, "f1");

    let predictions_only = [event(0, 0, 0.0, 1.0)];
    let only_predictions = run(&[], &predictions_only, &config(0.2, 0.2, 0.2));
    assert_close(only_predictions.precision, 0.0, "precision");
    assert_eq!(only_predictions.recall, None);
    assert_close(only_predictions.f1, 0.0, "f1");
}

#[test]
fn macro_f1_is_not_the_f1_of_macro_precision_and_recall() {
    // Class 0: 1 correct prediction, 10 references. Class 1: the mirror image.
    let mut references = vec![event(0, 0, 0.0, 1.0)];
    for index in 1..10 {
        references.push(event(0, 0, index as f64 * 2.0, index as f64 * 2.0 + 1.0));
    }
    references.push(event(0, 1, 0.0, 1.0));

    let mut predictions = vec![event(0, 0, 0.0, 1.0)];
    for index in 1..10 {
        predictions.push(event(0, 1, index as f64 * 2.0, index as f64 * 2.0 + 1.0));
    }
    predictions.push(event(0, 1, 0.0, 1.0));

    let mut config = config(0.2, 0.2, 0.2);
    config.average = Averaging::Macro;
    let result = run(&references, &predictions, &config);

    assert_eq!(result.n_correct, 2);
    let class_zero = &result.classes[0];
    assert_close(class_zero.precision, 1.0, "class 0 precision");
    assert_close(class_zero.recall, 0.1, "class 0 recall");

    assert_close(result.precision, 0.55, "macro precision");
    assert_close(result.recall, 0.55, "macro recall");
    assert_close(result.f1, 2.0 / 11.0, "macro f1");
}

#[test]
fn micro_pools_counts_across_classes() {
    let references = [
        event(0, 0, 0.0, 1.0),
        event(0, 0, 2.0, 3.0),
        event(0, 0, 4.0, 5.0),
        event(0, 1, 0.0, 1.0),
    ];
    let predictions = [
        event(0, 0, 0.0, 1.0),
        event(0, 1, 0.0, 1.0),
        event(0, 1, 6.0, 7.0),
        event(0, 1, 8.0, 9.0),
    ];

    let result = run(&references, &predictions, &config(0.2, 0.2, 0.2));

    assert_eq!(result.n_correct, 2);
    assert_close(result.precision, 2.0 / 4.0, "precision");
    assert_close(result.recall, 2.0 / 4.0, "recall");
    assert_close(result.f1, 2.0 / 4.0, "f1");
}

#[test]
fn recording_boundaries_are_validated() {
    let recordings = [Recording {
        recording_id: 0,
        duration: 5.0,
    }];
    let references = [event(0, 0, 4.0, 5.0)];
    let predictions = [event(0, 0, 4.0, 5.0)];

    let result = event_f1(
        &references,
        &predictions,
        &config(0.2, 0.2, 0.2),
        Some(&recordings),
    )
    .expect("events ending exactly at the recording end are valid");
    assert_eq!(result.n_correct, 1);

    let too_long = [event(0, 0, 4.5, 5.5)];
    let error = event_f1(
        &references,
        &too_long,
        &config(0.2, 0.2, 0.2),
        Some(&recordings),
    )
    .unwrap_err();
    assert!(matches!(error, ValidationError::OutsideRecording { .. }));
}

#[test]
fn malformed_events_are_rejected() {
    let config = config(0.2, 0.2, 0.2);

    let nan_onset = [event(0, 0, f64::NAN, 1.0)];
    assert!(matches!(
        event_f1(&nan_onset, &[], &config, None).unwrap_err(),
        ValidationError::NonFiniteTime { field: "onset", .. }
    ));

    let empty = [event(0, 0, 1.0, 1.0)];
    assert!(matches!(
        event_f1(&[], &empty, &config, None).unwrap_err(),
        ValidationError::EmptyInterval { .. }
    ));

    let negative = [event(0, 0, -0.5, 1.0)];
    assert!(matches!(
        event_f1(&negative, &[], &config, None).unwrap_err(),
        ValidationError::NegativeOnset { .. }
    ));

    let recordings = [Recording {
        recording_id: 0,
        duration: 1.0,
    }];
    let unknown = [event(7, 0, 0.0, 0.5)];
    assert!(matches!(
        event_f1(&unknown, &[], &config, Some(&recordings)).unwrap_err(),
        ValidationError::UnknownRecording { .. }
    ));

    let duplicated = [
        Recording {
            recording_id: 0,
            duration: 1.0,
        },
        Recording {
            recording_id: 0,
            duration: 2.0,
        },
    ];
    assert!(matches!(
        event_f1(&[], &[], &config, Some(&duplicated)).unwrap_err(),
        ValidationError::DuplicateRecording { .. }
    ));
}

#[test]
fn invalid_collars_are_rejected() {
    assert!(matches!(
        event_f1(&[], &[], &config(-0.1, 0.2, 0.2), None).unwrap_err(),
        ValidationError::InvalidCollar {
            field: "onset_collar",
            ..
        }
    ));
    assert!(matches!(
        event_f1(&[], &[], &config(0.2, f64::INFINITY, 0.2), None).unwrap_err(),
        ValidationError::InvalidCollar {
            field: "offset_collar",
            ..
        }
    ));
}

/// Brute-force oracle for maximum bipartite matching cardinality.
fn brute_force_cardinality(
    references: &[Event],
    predictions: &[Event],
    config: &CollarConfig,
) -> usize {
    fn search(
        reference_index: usize,
        references: &[Event],
        predictions: &[Event],
        config: &CollarConfig,
        used: &mut [bool],
        matched: usize,
        best: &mut usize,
    ) {
        if reference_index == references.len() {
            *best = (*best).max(matched);
            return;
        }
        search(
            reference_index + 1,
            references,
            predictions,
            config,
            used,
            matched,
            best,
        );
        for prediction_index in 0..predictions.len() {
            if used[prediction_index]
                || !sedmetrics::is_eligible(
                    &references[reference_index],
                    &predictions[prediction_index],
                    config,
                )
            {
                continue;
            }
            used[prediction_index] = true;
            search(
                reference_index + 1,
                references,
                predictions,
                config,
                used,
                matched + 1,
                best,
            );
            used[prediction_index] = false;
        }
    }

    let mut used = vec![false; predictions.len()];
    let mut best = 0;
    search(0, references, predictions, config, &mut used, 0, &mut best);
    best
}

#[test]
fn matching_cardinality_matches_a_brute_force_oracle() {
    // Deterministic xorshift so the test needs no dependency and is reproducible.
    let mut state = 0x2545_F491_4F6C_DD1D_u64;
    let mut next = || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        (state % 1000) as f64 / 100.0
    };

    let config = CollarConfig {
        onset_collar: 0.3,
        offset_collar: 0.3,
        offset_ratio: 0.1,
        evaluate_offset: true,
    };

    for trial in 0..200 {
        let reference_count = (trial % 5) + 1;
        let prediction_count = ((trial * 3) % 5) + 1;
        let references: Vec<Event> = (0..reference_count)
            .map(|_| {
                let onset = next();
                event(0, 0, onset, onset + 0.2 + next())
            })
            .collect();
        let predictions: Vec<Event> = (0..prediction_count)
            .map(|_| {
                let onset = next();
                event(0, 0, onset, onset + 0.2 + next())
            })
            .collect();

        let pairs = maximum_matching(&references, &predictions, &config);
        let expected = brute_force_cardinality(&references, &predictions, &config);

        assert_eq!(
            pairs.len(),
            expected,
            "trial {trial}: got {} matches, oracle says {expected}",
            pairs.len()
        );
        // Each index may appear at most once.
        let mut used_references: Vec<usize> = pairs.iter().map(|pair| pair.0).collect();
        let mut used_predictions: Vec<usize> = pairs.iter().map(|pair| pair.1).collect();
        used_references.sort_unstable();
        used_references.dedup();
        used_predictions.sort_unstable();
        used_predictions.dedup();
        assert_eq!(used_references.len(), pairs.len());
        assert_eq!(used_predictions.len(), pairs.len());
    }
}
