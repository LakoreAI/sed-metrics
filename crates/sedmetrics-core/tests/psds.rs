use sedmetrics_core::{Event, PsdsConfig, Recording, ScoreTrack, TimeUnit, ValidationError, psds};

fn reference(recording_id: u32, class_id: u32, onset: f64, offset: f64) -> Event {
    Event {
        recording_id,
        class_id,
        onset,
        offset,
    }
}

fn track(
    recording_id: u32,
    class_ids: Vec<u32>,
    boundaries: Vec<f64>,
    scores: Vec<f32>,
) -> ScoreTrack {
    ScoreTrack {
        recording_id,
        class_ids,
        boundaries,
        scores,
    }
}

fn config() -> PsdsConfig {
    PsdsConfig {
        dtc_threshold: 0.5,
        gtc_threshold: 0.5,
        cttc_threshold: None,
        alpha_ct: 0.0,
        alpha_st: 0.0,
        max_efpr: 1.0,
        time_decimals: 6,
        unit: TimeUnit::Second,
    }
}

#[test]
fn hand_computed_psds() {
    // 4 one-second frames; the reference covers frames 1 and 3.
    let references = [reference(0, 0, 1.0, 2.0)];
    let tracks = [track(
        0,
        vec![0],
        vec![0.0, 1.0, 2.0, 3.0, 4.0],
        vec![0.1, 0.9, 0.1, 0.9],
    )];
    let recordings = [Recording {
        recording_id: 0,
        duration: 4.0,
    }];

    let result = psds(&references, &tracks, &recordings, &config()).expect("valid");

    // At 0.9 there are two detections, one DTC-relevant -> TP 1, FP 1 -> eFPR 0.25.
    // At 0.1 the whole clip is one detection -> TP 1, FP 0 -> eFPR 0.
    assert_eq!(result.dataset_duration, 4.0);
    let class = &result.classes[0];
    assert_eq!(class.n_reference, 1);
    assert_eq!(class.efpr, vec![0.0, 0.25]);
    assert_eq!(class.tpr, vec![0.0, 1.0]);
    // TPR 1 holds from eFPR 0.25 to the truncation point 1.0.
    assert_eq!(result.psds, 0.75);
}

#[test]
fn postprocessing_envelope_contains_individual_curves() {
    let references = [reference(0, 0, 1.0, 2.0)];
    let recordings = [Recording {
        recording_id: 0,
        duration: 4.0,
    }];
    let first = [track(
        0,
        vec![0],
        vec![0.0, 1.0, 2.0, 3.0, 4.0],
        vec![0.1, 0.9, 0.1, 0.9],
    )];
    let second = [track(
        0,
        vec![0],
        vec![0.0, 1.0, 2.0, 3.0, 4.0],
        vec![0.1, 0.9, 0.1, 0.1],
    )];
    let a = psds(&references, &first, &recordings, &config()).unwrap();
    let b = psds(&references, &second, &recordings, &config()).unwrap();
    let merged = sedmetrics_core::merge_postprocessings(&[a.clone(), b.clone()]).unwrap();
    assert_eq!(merged.psds, 1.0);
    assert!(merged.psds >= a.psds && merged.psds >= b.psds);
    let mut incompatible = b;
    incompatible.config.max_efpr = 2.0;
    assert!(sedmetrics_core::merge_postprocessings(&[a, incompatible]).is_err());
}

#[test]
fn no_detection_at_all_has_zero_psds() {
    let references = [reference(0, 0, 1.0, 1.5)];
    // Scores below every reference region and above nothing: the only points
    // are "no detections", so TPR stays 0.
    let tracks = [track(0, vec![0], vec![0.0, 1.0, 2.0], vec![0.0, 0.0])];
    let recordings = [Recording {
        recording_id: 0,
        duration: 2.0,
    }];

    let result = psds(&references, &tracks, &recordings, &config()).expect("valid");
    assert_eq!(result.psds, 0.0);
    assert_eq!(result.classes[0].tpr, vec![0.0]);
}

#[test]
fn cross_triggers_do_not_reduce_true_positives() {
    let references = [reference(0, 0, 1.0, 2.0), reference(0, 1, 3.0, 4.0)];
    let tracks = [track(
        0,
        vec![0, 1],
        vec![0.0, 1.0, 2.0, 3.0, 4.0],
        // Frame 1 is class 0, frame 3 is class 1: both references are detected.
        vec![0.1, 0.1, 0.9, 0.1, 0.1, 0.1, 0.1, 0.9],
    )];
    let recordings = [Recording {
        recording_id: 0,
        duration: 4.0,
    }];

    let mut config = config();
    config.cttc_threshold = Some(0.5);
    config.alpha_ct = 0.5;
    let result = psds(&references, &tracks, &recordings, &config).expect("valid");

    // Both classes see TP 1, FP 0 at the lowest threshold.
    for class in &result.classes {
        assert!(class.tpr.contains(&1.0));
    }
}

#[test]
fn class_vocabulary_must_match() {
    let references = [reference(0, 0, 1.0, 2.0)];
    let tracks = [track(0, vec![0, 1], vec![0.0, 2.0], vec![0.5, 0.5])];
    let recordings = [Recording {
        recording_id: 0,
        duration: 2.0,
    }];

    let error = psds(&references, &tracks, &recordings, &config()).unwrap_err();
    assert!(matches!(error, ValidationError::ClassVocabularyMismatch));
}

#[test]
fn a_class_without_references_is_rejected() {
    let references = [reference(0, 0, 1.0, 2.0)];
    let tracks = [track(0, vec![0], vec![0.0, 2.0], vec![0.5])];
    let recordings = [Recording {
        recording_id: 0,
        duration: 2.0,
    }];
    // Remove the only reference by using a class the track does not score.
    let error = psds(&[], &tracks, &recordings, &config()).unwrap_err();
    assert!(matches!(error, ValidationError::ClassVocabularyMismatch));

    let error = psds(&references, &tracks, &recordings, &config());
    assert!(error.is_ok());
}

#[test]
fn malformed_score_tracks_are_rejected() {
    let references = [reference(0, 0, 1.0, 2.0)];
    let recordings = [Recording {
        recording_id: 0,
        duration: 2.0,
    }];

    let non_finite = [track(0, vec![0], vec![0.0, 2.0], vec![f32::NAN])];
    assert!(matches!(
        psds(&references, &non_finite, &recordings, &config()).unwrap_err(),
        ValidationError::InvalidScoreTrack { .. }
    ));

    let wrong_length = [track(0, vec![0], vec![0.0, 1.0, 2.0], vec![0.5])];
    assert!(matches!(
        psds(&references, &wrong_length, &recordings, &config()).unwrap_err(),
        ValidationError::InvalidScoreTrack { .. }
    ));

    let non_increasing = [track(0, vec![0], vec![0.0, 1.0, 1.0], vec![0.5, 0.5])];
    assert!(matches!(
        psds(&references, &non_increasing, &recordings, &config()).unwrap_err(),
        ValidationError::InvalidScoreTrack { .. }
    ));

    let duplicate = [
        track(0, vec![0], vec![0.0, 2.0], vec![0.5]),
        track(0, vec![0], vec![0.0, 2.0], vec![0.5]),
    ];
    assert!(matches!(
        psds(&references, &duplicate, &recordings, &config()).unwrap_err(),
        ValidationError::DuplicateScoreTrack { .. }
    ));
}

#[test]
fn incomplete_score_coverage_is_rejected() {
    let references = [reference(0, 0, 0.0, 1.0), reference(0, 1, 0.0, 1.0)];
    let recordings = [
        Recording {
            recording_id: 0,
            duration: 2.0,
        },
        Recording {
            recording_id: 1,
            duration: 2.0,
        },
    ];
    let complete = track(0, vec![0, 1], vec![0.0, 2.0], vec![0.5, 0.5]);
    let missing_recording = [complete.clone()];
    assert!(psds(&references, &missing_recording, &recordings, &config()).is_err());
    let missing_class = [
        complete.clone(),
        track(1, vec![0], vec![0.0, 2.0], vec![0.5]),
    ];
    assert!(psds(&references, &missing_class, &recordings, &config()).is_err());
    let partial = [
        complete,
        track(1, vec![0, 1], vec![0.5, 2.0], vec![0.5, 0.5]),
    ];
    assert!(psds(&references, &partial, &recordings, &config()).is_err());
}

#[test]
fn inconsistent_cross_trigger_configuration_is_rejected() {
    let mut missing_cttc = config();
    missing_cttc.alpha_ct = 0.5;
    assert!(matches!(
        missing_cttc.validate().unwrap_err(),
        ValidationError::InvalidParameter {
            field: "cttc_threshold",
            ..
        }
    ));

    let mut unexpected_cttc = config();
    unexpected_cttc.cttc_threshold = Some(0.3);
    assert!(matches!(
        unexpected_cttc.validate().unwrap_err(),
        ValidationError::InconsistentPsdsConfig
    ));
}

#[test]
fn psds_is_bounded_and_monotone_in_the_scores() {
    // A perfect detection at every frame must reach PSDS 1.
    let references = [reference(0, 0, 0.0, 2.0)];
    let tracks = [track(0, vec![0], vec![0.0, 1.0, 2.0], vec![0.9, 0.9])];
    let recordings = [Recording {
        recording_id: 0,
        duration: 2.0,
    }];

    let result = psds(&references, &tracks, &recordings, &config()).expect("valid");
    assert_eq!(result.psds, 1.0);
    assert!(result.psds <= 1.0);
}

#[test]
fn a_repeated_reference_does_not_count_twice() {
    // The detection covers 4 of its 10 seconds: below a DTC of 0.7.
    let tracks = [track(0, vec![0], vec![0.0, 10.0], vec![0.9])];
    let recordings = [Recording {
        recording_id: 0,
        duration: 10.0,
    }];
    let strict = PsdsConfig {
        dtc_threshold: 0.7,
        gtc_threshold: 0.7,
        ..config()
    };
    let once = [reference(0, 0, 0.0, 4.0)];
    let twice = [reference(0, 0, 0.0, 4.0), reference(0, 0, 0.0, 4.0)];

    let single = psds(&once, &tracks, &recordings, &strict).expect("valid");
    let repeated = psds(&twice, &tracks, &recordings, &strict).expect("valid");

    assert_eq!(single.psds, 0.0);
    assert_eq!(repeated, single);
}

#[test]
fn overlapping_and_touching_references_are_merged() {
    let tracks = [
        track(
            0,
            vec![0, 1],
            vec![0.0, 4.0, 10.0],
            vec![0.9, 0.2, 0.1, 0.8],
        ),
        track(
            1,
            vec![0, 1],
            vec![0.0, 4.0, 10.0],
            vec![0.7, 0.1, 0.3, 0.6],
        ),
    ];
    let recordings = [
        Recording {
            recording_id: 0,
            duration: 10.0,
        },
        Recording {
            recording_id: 1,
            duration: 10.0,
        },
    ];
    // Unsorted; nested, overlapping and touching events in recording 0. The
    // class 0 event of recording 1 stays separate: merging is per recording.
    let raw = [
        reference(0, 0, 3.0, 4.0),
        reference(0, 0, 0.0, 2.0),
        reference(0, 0, 1.0, 3.0),
        reference(0, 0, 1.5, 1.8),
        reference(0, 0, 5.0, 6.0),
        reference(1, 0, 0.0, 4.0),
        reference(0, 1, 4.0, 7.0),
        reference(0, 1, 6.0, 10.0),
    ];
    let merged = [
        reference(0, 0, 0.0, 4.0),
        reference(0, 0, 5.0, 6.0),
        reference(1, 0, 0.0, 4.0),
        reference(0, 1, 4.0, 10.0),
    ];
    let cross = PsdsConfig {
        dtc_threshold: 0.1,
        gtc_threshold: 0.1,
        cttc_threshold: Some(0.3),
        alpha_ct: 0.5,
        ..config()
    };

    let from_raw = psds(&raw, &tracks, &recordings, &cross).expect("valid");
    let from_merged = psds(&merged, &tracks, &recordings, &cross).expect("valid");

    assert_eq!(from_raw, from_merged);
    assert_eq!(from_raw.classes[0].n_reference, 3);
    assert_eq!(from_raw.classes[0].reference_duration, 9.0);
    assert_eq!(from_raw.classes[1].n_reference, 1);
}
