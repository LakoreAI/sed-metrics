use sedmetrics::frame_metrics;

#[test]
fn hand_calculation_and_ties() {
    let result = frame_metrics(&[true, false, true], &[0.9, 0.8, 0.1], &[1.0; 3], 0.5).unwrap();
    assert_eq!(
        (result.tp, result.fp, result.fn_, result.tn),
        (1.0, 1.0, 1.0, 0.0)
    );
    assert!((result.average_precision.unwrap() - 5.0 / 6.0).abs() < 1e-12);
    assert_eq!(result.auroc, Some(0.5));
    let tied = frame_metrics(&[true, false], &[0.5, 0.5], &[1.0, 2.0], 0.5).unwrap();
    assert_eq!(tied.average_precision, Some(1.0 / 3.0));
    assert_eq!(tied.auroc, Some(0.5));
}

#[test]
fn rejects_invalid_data_and_reports_undefined() {
    assert!(frame_metrics(&[true], &[], &[1.0], 0.0).is_err());
    assert!(frame_metrics(&[true], &[f64::NAN], &[1.0], 0.0).is_err());
    assert!(frame_metrics(&[true], &[1.0], &[0.0], 0.0).is_err());
    let empty = frame_metrics(&[], &[], &[], 0.0).unwrap();
    assert_eq!(empty.f1, None);
    assert_eq!(empty.average_precision, None);
    assert_eq!(empty.auroc, None);
}
