//! Proper scoring rules for aligned binary probabilities and soft targets.

/// Mean Brier score and its numerator and exposure.
#[derive(Debug, Clone, PartialEq)]
pub struct BrierResult {
    /// Sum of weighted squared differences.
    pub squared_error: f64,
    /// Sum of weights.
    pub weight: f64,
    /// Weighted mean, or None for an empty input.
    pub brier: Option<f64>,
}

/// Weighted mean squared difference of probabilities and soft targets.
pub fn brier(
    targets: &[f64],
    probabilities: &[f64],
    weights: &[f64],
) -> Result<BrierResult, &'static str> {
    if targets.len() != probabilities.len() || targets.len() != weights.len() {
        return Err("targets, probabilities and weights must have equal lengths");
    }
    let (mut squared_error, mut weight) = (0.0, 0.0);
    for ((&target, &probability), &w) in targets.iter().zip(probabilities).zip(weights) {
        if !target.is_finite() || !(0.0..=1.0).contains(&target) {
            return Err("targets must be finite and in [0, 1]");
        }
        if !probability.is_finite() || !(0.0..=1.0).contains(&probability) {
            return Err("probabilities must be finite and in [0, 1]");
        }
        if !w.is_finite() || w <= 0.0 {
            return Err("weights must be finite and positive");
        }
        squared_error += w * (probability - target).powi(2);
        weight += w;
    }
    if !weight.is_finite() || !squared_error.is_finite() {
        return Err("total weight and squared error must be finite");
    }
    Ok(BrierResult {
        squared_error,
        weight,
        brier: if weight > 0.0 {
            Some(squared_error / weight)
        } else {
            None
        },
    })
}
