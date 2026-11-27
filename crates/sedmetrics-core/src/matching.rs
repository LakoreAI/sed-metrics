//! Collar-based event eligibility and one-to-one matching.
//!
//! Matching policy is not shared with intersection-based evaluation (PSDS): a
//! pairwise overlap matcher is not a substitute for either protocol, and the two
//! must not be forced through a single generic matcher.

use crate::types::Event;
use crate::validation::ValidationError;

/// Collar configuration for event-based evaluation.
///
/// A prediction is eligible for a reference when the classes and recordings
/// agree, the absolute onset difference is at most [`CollarConfig::onset_collar`],
/// and (when [`CollarConfig::evaluate_offset`] is set) the absolute offset
/// difference is at most `max(offset_collar, offset_ratio * reference_duration)`.
///
/// Comparisons are exact (`<=`) with no floating-point epsilon, so exact-boundary
/// behaviour is reproducible and testable.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CollarConfig {
    /// Onset tolerance in seconds. Must be finite and nonnegative.
    pub onset_collar: f64,
    /// Absolute offset tolerance in seconds. Must be finite and nonnegative.
    pub offset_collar: f64,
    /// Offset tolerance as a fraction of the reference event duration.
    /// Must be finite and nonnegative.
    pub offset_ratio: f64,
    /// Whether offset agreement is required. When false, only onsets are
    /// evaluated (a documented onset-only protocol).
    pub evaluate_offset: bool,
}

impl Default for CollarConfig {
    /// The collars used by the `dcase2016` profile: 200 ms onset,
    /// `max(200 ms, 20 % of reference duration)` offset, offset evaluated.
    fn default() -> Self {
        Self {
            onset_collar: 0.2,
            offset_collar: 0.2,
            offset_ratio: 0.2,
            evaluate_offset: true,
        }
    }
}

impl CollarConfig {
    /// Offset tolerance for a reference event of the given duration.
    pub fn offset_tolerance(&self, reference_duration: f64) -> f64 {
        self.offset_collar
            .max(self.offset_ratio * reference_duration)
    }

    /// Check that all collar parameters are finite and nonnegative.
    pub fn validate(&self) -> Result<(), ValidationError> {
        for (field, value) in [
            ("onset_collar", self.onset_collar),
            ("offset_collar", self.offset_collar),
            ("offset_ratio", self.offset_ratio),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(ValidationError::InvalidCollar { field, value });
            }
        }
        Ok(())
    }
}

/// Whether `prediction` is eligible for `reference` under `config`.
pub fn is_eligible(reference: &Event, prediction: &Event, config: &CollarConfig) -> bool {
    if reference.recording_id != prediction.recording_id
        || reference.class_id != prediction.class_id
    {
        return false;
    }
    if (prediction.onset - reference.onset).abs() > config.onset_collar {
        return false;
    }
    if config.evaluate_offset {
        let tolerance = config.offset_tolerance(reference.duration());
        if (prediction.offset - reference.offset).abs() > tolerance {
            return false;
        }
    }
    true
}

/// Maximum-cardinality one-to-one matching within one recording and class.
///
/// Uses augmenting paths (Kuhn's algorithm), which returns a maximum-cardinality
/// matching; a greedy assignment can lose valid true positives.
///
/// Determinism: the result is a function of the input order only. Iterating
/// references and predictions in their given order, with the lowest-index
/// prediction preferred whenever a choice exists, yields a stable matching for
/// identical inputs. Callers that need permutation invariance of the *pairs*
/// (not just the counts) must order their inputs canonically.
///
/// The secondary objective is not total localization error: among
/// maximum-cardinality matchings this function does not minimize the summed
/// onset/offset error, and it must not be described as doing so.
///
/// Returns `(reference_index, prediction_index)` pairs sorted by reference index.
///
/// Complexity is `O(V * E)` in the worst case with recursion depth bounded by the
/// number of references in the group.
pub fn maximum_matching(
    references: &[Event],
    predictions: &[Event],
    config: &CollarConfig,
) -> Vec<(usize, usize)> {
    let mut owner: Vec<Option<usize>> = vec![None; predictions.len()];

    for reference_index in 0..references.len() {
        let mut visited = vec![false; predictions.len()];
        augment(
            reference_index,
            references,
            predictions,
            config,
            &mut owner,
            &mut visited,
        );
    }

    let mut pairs: Vec<(usize, usize)> = owner
        .iter()
        .enumerate()
        .filter_map(|(prediction_index, owner)| {
            owner.map(|reference_index| (reference_index, prediction_index))
        })
        .collect();
    pairs.sort_unstable();
    pairs
}

fn augment(
    reference_index: usize,
    references: &[Event],
    predictions: &[Event],
    config: &CollarConfig,
    owner: &mut [Option<usize>],
    visited: &mut [bool],
) -> bool {
    for prediction_index in 0..predictions.len() {
        if visited[prediction_index] {
            continue;
        }
        if !is_eligible(
            &references[reference_index],
            &predictions[prediction_index],
            config,
        ) {
            continue;
        }
        visited[prediction_index] = true;
        match owner[prediction_index] {
            None => {
                owner[prediction_index] = Some(reference_index);
                return true;
            }
            Some(other) => {
                if augment(other, references, predictions, config, owner, visited) {
                    owner[prediction_index] = Some(reference_index);
                    return true;
                }
            }
        }
    }
    false
}
