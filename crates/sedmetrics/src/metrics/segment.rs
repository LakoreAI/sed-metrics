//! Segment-based (frame-block) metrics: precision, recall, F1 and the
//! substitution/deletion/insertion decomposition.
//!
//! Specification: `docs/metrics/segment_f1.md`.

use std::collections::BTreeMap;

use crate::types::{Event, Recording};
use crate::validation::{ValidationError, validate_events, validate_recordings};

use super::event::Averaging;

/// Configuration for segment-based evaluation.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SegmentConfig {
    /// Segment length in seconds. Must be finite and positive.
    pub segment_length: f64,
    /// Class aggregation for the reported ratios.
    pub average: Averaging,
}

impl Default for SegmentConfig {
    /// One-second segments, micro averaging: the DCASE / `sed_eval` baseline.
    fn default() -> Self {
        Self {
            segment_length: 1.0,
            average: Averaging::Micro,
        }
    }
}

impl SegmentConfig {
    /// Check the segment length.
    pub fn validate(&self) -> Result<(), ValidationError> {
        if !self.segment_length.is_finite() || self.segment_length <= 0.0 {
            return Err(ValidationError::InvalidParameter {
                field: "segment_length",
                value: self.segment_length,
            });
        }
        Ok(())
    }
}

/// Per-class segment statistics. All counts are whole segments.
#[derive(Debug, Clone, PartialEq)]
pub struct ClassSegmentMetrics {
    /// Class identifier.
    pub class_id: u32,
    /// Segments active in both reference and prediction.
    pub n_true_positive: u64,
    /// Segments active only in the prediction.
    pub n_false_positive: u64,
    /// Segments active only in the reference.
    pub n_false_negative: u64,
    /// Active reference segments.
    pub n_reference: u64,
    /// Active predicted segments.
    pub n_predicted: u64,
    /// `TP / n_predicted`, `None` when nothing was predicted.
    pub precision: Option<f64>,
    /// `TP / n_reference`, `None` when the class has no reference activity.
    pub recall: Option<f64>,
    /// F1 from counts, `None` when both sides are empty.
    pub f1: Option<f64>,
}

/// Aggregate segment result, including the error-rate decomposition.
#[derive(Debug, Clone, PartialEq)]
pub struct SegmentResult {
    /// Aggregation used for the reported ratios.
    pub average: Averaging,
    /// Segments active in both reference and prediction.
    pub n_true_positive: u64,
    /// Segments active only in the prediction.
    pub n_false_positive: u64,
    /// Segments active only in the reference.
    pub n_false_negative: u64,
    /// Active reference segments; denominator of all rates.
    pub n_reference: u64,
    /// Active predicted segments.
    pub n_predicted: u64,
    /// Precision under the configured averaging.
    pub precision: Option<f64>,
    /// Recall under the configured averaging.
    pub recall: Option<f64>,
    /// F1 under the configured averaging.
    pub f1: Option<f64>,
    /// Segments where both sides are active but disagree on the class.
    pub n_substitutions: u64,
    /// Reference-active segments without any predicted activity.
    pub n_deletions: u64,
    /// Predicted-active segments without any reference activity.
    pub n_insertions: u64,
    /// `(S + D + I) / n_reference`; can exceed 1.
    pub error_rate: Option<f64>,
    /// `S / n_reference`.
    pub substitution_rate: Option<f64>,
    /// `D / n_reference`.
    pub deletion_rate: Option<f64>,
    /// `I / n_reference`.
    pub insertion_rate: Option<f64>,
    /// Evaluated segments across recordings.
    pub n_segments: u64,
    /// Number of distinct classes present in references or predictions.
    pub n_classes: u64,
    /// Per-class statistics, sorted by class id.
    pub classes: Vec<ClassSegmentMetrics>,
    /// Configuration used.
    pub config: SegmentConfig,
}

/// Half-open segment ranges `[start, end)` in segment indices.
type Ranges = Vec<(i64, i64)>;

fn to_ranges(times: &[(f64, f64)], segment_length: f64, n_segments: i64) -> Ranges {
    let mut ranges: Ranges = Vec::with_capacity(times.len());
    for &(onset, offset) in times {
        // Reference protocol: floor the onset and ceil the offset, so a segment
        // is active when any part of it is covered and a shared endpoint alone
        // does not activate one.
        let start = ((onset / segment_length).floor() as i64).max(0);
        let end = ((offset / segment_length).ceil() as i64).min(n_segments);
        if start < end {
            ranges.push((start, end));
        }
    }
    ranges.sort_unstable();
    let mut merged: Ranges = Vec::with_capacity(ranges.len());
    for (start, end) in ranges {
        match merged.last_mut() {
            Some(last) if start <= last.1 => last.1 = last.1.max(end),
            _ => merged.push((start, end)),
        }
    }
    merged
}

fn total_length(ranges: &Ranges) -> u64 {
    ranges.iter().map(|(start, end)| (end - start) as u64).sum()
}

fn intersections(left: &Ranges, right: &Ranges) -> Ranges {
    let (mut i, mut j) = (0, 0);
    let mut result: Ranges = Vec::new();
    while i < left.len() && j < right.len() {
        let start = left[i].0.max(right[j].0);
        let end = left[i].1.min(right[j].1);
        if start < end {
            result.push((start, end));
        }
        if left[i].1 <= right[j].1 {
            i += 1;
        } else {
            j += 1;
        }
    }
    result
}

#[derive(Default, Clone, Copy)]
struct Delta {
    reference: i64,
    predicted: i64,
    both: i64,
}

fn ratio(numerator: u64, denominator: u64) -> Option<f64> {
    if denominator == 0 {
        None
    } else {
        Some(numerator as f64 / denominator as f64)
    }
}

/// Compute segment-based precision, recall, F1 and the S/D/I decomposition.
///
/// A segment `[k * segment_length, (k + 1) * segment_length)` is active for a
/// class when at least one event of that class overlaps it. Segment indices use
/// `floor(onset / length)` and `ceil(offset / length)`.
///
/// The evaluated length of a recording is its duration when `recordings` is
/// given, otherwise the latest offset among its reference and predicted events.
/// Activity past that length is ignored.
pub fn segment_metrics(
    references: &[Event],
    predictions: &[Event],
    config: &SegmentConfig,
    recordings: Option<&[Recording]>,
) -> Result<SegmentResult, ValidationError> {
    config.validate()?;
    if let Some(recordings) = recordings {
        validate_recordings(recordings)?;
    }
    validate_events(references, recordings)?;
    validate_events(predictions, recordings)?;

    // Raw intervals grouped by recording, then class.
    type ClassTimes = (Vec<(f64, f64)>, Vec<(f64, f64)>);
    let mut by_recording: BTreeMap<u32, BTreeMap<u32, ClassTimes>> = BTreeMap::new();
    for event in references {
        by_recording
            .entry(event.recording_id)
            .or_default()
            .entry(event.class_id)
            .or_default()
            .0
            .push((event.onset, event.offset));
    }
    for event in predictions {
        by_recording
            .entry(event.recording_id)
            .or_default()
            .entry(event.class_id)
            .or_default()
            .1
            .push((event.onset, event.offset));
    }

    // (true positives, false positives, false negatives) per class.
    let mut per_class: BTreeMap<u32, (u64, u64, u64)> = BTreeMap::new();
    let mut substitutions: u64 = 0;
    let mut deletions: u64 = 0;
    let mut insertions: u64 = 0;

    for (recording_id, classes) in &by_recording {
        let length = match recordings {
            Some(recordings) => recordings
                .iter()
                .find(|recording| recording.recording_id == *recording_id)
                .map(|recording| recording.duration)
                .expect("recording was validated"),
            None => classes
                .values()
                .flat_map(|(reference, predicted)| reference.iter().chain(predicted))
                .map(|(_, offset)| *offset)
                .fold(0.0, f64::max),
        };
        let segments = (length / config.segment_length).ceil() as i64;

        let mut delta: BTreeMap<i64, Delta> = BTreeMap::new();
        for (class_id, (reference_times, prediction_times)) in classes {
            let reference_ranges = to_ranges(reference_times, config.segment_length, segments);
            let prediction_ranges = to_ranges(prediction_times, config.segment_length, segments);
            let shared = intersections(&reference_ranges, &prediction_ranges);
            let true_positives = total_length(&shared);

            let entry = per_class.entry(*class_id).or_insert((0, 0, 0));
            entry.0 += true_positives;
            entry.1 += total_length(&prediction_ranges) - true_positives;
            entry.2 += total_length(&reference_ranges) - true_positives;

            for (start, end) in &reference_ranges {
                delta.entry(*start).or_default().reference += 1;
                delta.entry(*end).or_default().reference -= 1;
            }
            for (start, end) in &prediction_ranges {
                delta.entry(*start).or_default().predicted += 1;
                delta.entry(*end).or_default().predicted -= 1;
            }
            for (start, end) in &shared {
                delta.entry(*start).or_default().both += 1;
                delta.entry(*end).or_default().both -= 1;
            }
        }

        // Sweep the recording's boundaries: between two consecutive boundary
        // points every segment has the same reference/predicted/overlap counts.
        let points: Vec<i64> = delta.keys().copied().collect();
        let (mut active_reference, mut active_predicted, mut active_both) = (0_i64, 0_i64, 0_i64);
        for (index, point) in points.iter().enumerate() {
            let change = delta[point];
            active_reference += change.reference;
            active_predicted += change.predicted;
            active_both += change.both;
            if index + 1 == points.len() {
                break;
            }
            let width = (points[index + 1] - point) as u64;
            let reference = active_reference.max(0) as u64;
            let predicted = active_predicted.max(0) as u64;
            let both = active_both.max(0) as u64;
            substitutions += width * (reference.min(predicted).saturating_sub(both));
            deletions += width * reference.saturating_sub(predicted);
            insertions += width * predicted.saturating_sub(reference);
        }
    }

    let classes: Vec<ClassSegmentMetrics> = per_class
        .iter()
        .map(
            |(class_id, (true_positive, false_positive, false_negative))| {
                let reference = true_positive + false_negative;
                let predicted = true_positive + false_positive;
                ClassSegmentMetrics {
                    class_id: *class_id,
                    n_true_positive: *true_positive,
                    n_false_positive: *false_positive,
                    n_false_negative: *false_negative,
                    n_reference: reference,
                    n_predicted: predicted,
                    precision: ratio(*true_positive, predicted),
                    recall: ratio(*true_positive, reference),
                    f1: ratio(
                        2 * true_positive,
                        2 * true_positive + false_positive + false_negative,
                    ),
                }
            },
        )
        .collect();

    let true_positives: u64 = per_class.values().map(|counts| counts.0).sum();
    let false_positives: u64 = per_class.values().map(|counts| counts.1).sum();
    let false_negatives: u64 = per_class.values().map(|counts| counts.2).sum();
    let reference_segments = true_positives + false_negatives;
    let predicted_segments = true_positives + false_positives;

    let (precision, recall, f1) = match config.average {
        Averaging::Micro => (
            ratio(true_positives, predicted_segments),
            ratio(true_positives, reference_segments),
            ratio(
                2 * true_positives,
                2 * true_positives + false_positives + false_negatives,
            ),
        ),
        Averaging::Macro => (
            mean_defined(&classes, |class| class.precision),
            mean_defined(&classes, |class| class.recall),
            mean_defined(&classes, |class| class.f1),
        ),
    };

    let n_segments: u64 = match recordings {
        Some(recordings) => recordings
            .iter()
            .map(|recording| {
                ((recording.duration / config.segment_length).ceil() as i64).max(0) as u64
            })
            .sum(),
        None => by_recording
            .values()
            .map(|classes| {
                let length = classes
                    .values()
                    .flat_map(|(reference, predicted)| reference.iter().chain(predicted))
                    .map(|(_, offset)| *offset)
                    .fold(0.0, f64::max);
                ((length / config.segment_length).ceil() as i64).max(0) as u64
            })
            .sum(),
    };

    let error_count = substitutions + deletions + insertions;
    Ok(SegmentResult {
        average: config.average,
        n_true_positive: true_positives,
        n_false_positive: false_positives,
        n_false_negative: false_negatives,
        n_reference: reference_segments,
        n_predicted: predicted_segments,
        precision,
        recall,
        f1,
        n_substitutions: substitutions,
        n_deletions: deletions,
        n_insertions: insertions,
        error_rate: ratio(error_count, reference_segments),
        substitution_rate: ratio(substitutions, reference_segments),
        deletion_rate: ratio(deletions, reference_segments),
        insertion_rate: ratio(insertions, reference_segments),
        n_segments,
        n_classes: classes.len() as u64,
        classes,
        config: *config,
    })
}

fn mean_defined<F>(classes: &[ClassSegmentMetrics], select: F) -> Option<f64>
where
    F: Fn(&ClassSegmentMetrics) -> Option<f64>,
{
    let mut sum = 0.0;
    let mut count = 0_u64;
    for class in classes {
        if let Some(value) = select(class) {
            sum += value;
            count += 1;
        }
    }
    if count == 0 {
        None
    } else {
        Some(sum / count as f64)
    }
}
