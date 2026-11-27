use sedmetrics_core::brier;

#[test]
fn brier_hand_example_and_invalid_inputs() {
    let result = brier(&[1.0, 0.0], &[0.8, 0.1], &[1.0, 1.0]).unwrap();
    assert!((result.brier.unwrap() - 0.025).abs() < 1e-12);
    assert_eq!(brier(&[], &[], &[]).unwrap().brier, None);
    assert!(brier(&[0.5], &[1.1], &[1.0]).is_err());
    assert!(brier(&[f64::NAN], &[0.5], &[1.0]).is_err());
}
