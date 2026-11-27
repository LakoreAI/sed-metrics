use sedmetrics_core::{CreateAlert, Event, Recording, evaluate_streaming};

#[test]
fn deadline_and_censoring_fixture() {
    let refs = [
        Event {
            recording_id: 0,
            class_id: 0,
            onset: 0.0,
            offset: 0.5,
        },
        Event {
            recording_id: 0,
            class_id: 0,
            onset: 2.0,
            offset: 2.5,
        },
        Event {
            recording_id: 0,
            class_id: 0,
            onset: 4.0,
            offset: 4.5,
        },
    ];
    let alerts = [
        CreateAlert {
            recording_id: 0,
            alert_id: 1,
            class_id: 0,
            emitted_at: 0.1,
            audio_available_until: 0.1,
            latest_audio_used: Some(0.1),
        },
        CreateAlert {
            recording_id: 0,
            alert_id: 2,
            class_id: 0,
            emitted_at: 2.4,
            audio_available_until: 2.4,
            latest_audio_used: Some(2.4),
        },
    ];
    let result = evaluate_streaming(
        &refs,
        &alerts,
        &[Recording {
            recording_id: 0,
            duration: 10.0,
        }],
        &[0],
        1.0,
        &[0.25, 0.5],
        1.0,
    )
    .unwrap();
    assert_eq!(result.n_matched, 2);
    assert!((result.audr.unwrap() - 0.5).abs() < 1e-12);
    assert_eq!(
        result.deadline_recall,
        vec![Some(1.0 / 3.0), Some(2.0 / 3.0)]
    );
}
