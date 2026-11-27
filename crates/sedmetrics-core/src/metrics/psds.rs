//! PSDS (Polyphonic Sound Detection Score) with intersection-based criteria.
//!
//! Specification: `docs/metrics/psds.md`.
//!
//! The criteria follow the intersection-based definition used by
//! `sed_scores_eval` (Bilen et al. 2020): a detection is relevant when the sum
//! of its intersections with same-class references covers a fraction of its own
//! length; a reference is a true positive when relevant detections cover a
//! fraction of its length. There is no one-to-one assignment anywhere.

use std::collections::{BTreeMap, BTreeSet};

use crate::types::{Event, Recording};
use crate::validation::{ValidationError, validate_events, validate_recordings};

/// Time unit for the effective false-positive rate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TimeUnit {
    /// Per second.
    Second,
    /// Per minute.
    Minute,
    /// Per hour (the DCASE convention).
    Hour,
}

impl TimeUnit {
    /// Seconds per unit: the multiplier applied to a rate per second.
    fn seconds_per_unit(self) -> f64 {
        match self {
            Self::Second => 1.0,
            Self::Minute => 60.0,
            Self::Hour => 3600.0,
        }
    }
}

/// PSDS configuration.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PsdsConfig {
    /// DTC threshold on the detection length (PSDS1/PSDS2: 0.7 / 0.1).
    pub dtc_threshold: f64,
    /// GTC threshold on the reference length (PSDS1/PSDS2: 0.7 / 0.1).
    pub gtc_threshold: f64,
    /// CTTC threshold on the detection length; required iff `alpha_ct > 0`.
    pub cttc_threshold: Option<f64>,
    /// Weight of the mean cross-trigger rate (PSDS1: 0, PSDS2: 0.5).
    pub alpha_ct: f64,
    /// Weight of the cross-class standard deviation (DCASE: 1.0).
    pub alpha_st: f64,
    /// Upper limit of the effective false-positive rate (DCASE: 100 / hour).
    pub max_efpr: f64,
    /// Decimal places used when rounding criterion sums (`sed_scores_eval`: 6).
    pub time_decimals: u32,
    /// Unit of the effective false-positive rate.
    pub unit: TimeUnit,
}

impl Default for PsdsConfig {
    /// The DCASE PSDS1 profile: DTC/GTC 0.7, no cross-triggers, alpha_st 1,
    /// 100 false positives per hour.
    fn default() -> Self {
        Self {
            dtc_threshold: 0.7,
            gtc_threshold: 0.7,
            cttc_threshold: None,
            alpha_ct: 0.0,
            alpha_st: 1.0,
            max_efpr: 100.0,
            time_decimals: 6,
            unit: TimeUnit::Hour,
        }
    }
}

impl PsdsConfig {
    /// The DCASE PSDS2 profile: DTC/GTC 0.1, CTTC 0.3, alpha_ct 0.5, alpha_st 1.
    pub fn psds2() -> Self {
        Self {
            dtc_threshold: 0.1,
            gtc_threshold: 0.1,
            cttc_threshold: Some(0.3),
            alpha_ct: 0.5,
            alpha_st: 1.0,
            max_efpr: 100.0,
            time_decimals: 6,
            unit: TimeUnit::Hour,
        }
    }

    /// Validate thresholds and weights.
    pub fn validate(&self) -> Result<(), ValidationError> {
        for (field, value) in [
            ("dtc_threshold", self.dtc_threshold),
            ("gtc_threshold", self.gtc_threshold),
            ("alpha_ct", self.alpha_ct),
            ("alpha_st", self.alpha_st),
            ("max_efpr", self.max_efpr),
        ] {
            if !value.is_finite() || value < 0.0 {
                return Err(ValidationError::InvalidParameter { field, value });
            }
        }
        if let Some(value) = self.cttc_threshold {
            if !value.is_finite() || value < 0.0 {
                return Err(ValidationError::InvalidParameter {
                    field: "cttc_threshold",
                    value,
                });
            }
        }
        if self.max_efpr <= 0.0 {
            return Err(ValidationError::InvalidParameter {
                field: "max_efpr",
                value: self.max_efpr,
            });
        }
        match (self.alpha_ct > 0.0, self.cttc_threshold) {
            (true, None) => {
                return Err(ValidationError::InvalidParameter {
                    field: "cttc_threshold",
                    value: 0.0,
                });
            }
            (false, Some(_)) => {
                // `sed_scores_eval` rejects this combination; so do we.
                return Err(ValidationError::InconsistentPsdsConfig);
            }
            _ => {}
        }
        Ok(())
    }
}

/// Frame-level scores for one recording.
///
/// `class_ids` names the score columns; `boundaries` has one more entry than
/// there are frames, and frame `i` covers `[boundaries[i], boundaries[i + 1])`.
/// `scores` is row-major `[frames, class_ids.len()]`.
#[derive(Debug, Clone, PartialEq)]
pub struct ScoreTrack {
    /// Recording the scores belong to.
    pub recording_id: u32,
    /// Class id for each score column, in column order.
    pub class_ids: Vec<u32>,
    /// Frame boundaries in seconds, strictly increasing.
    pub boundaries: Vec<f64>,
    /// Row-major scores; must be finite.
    pub scores: Vec<f32>,
}

impl ScoreTrack {
    /// Number of frames.
    pub fn n_frames(&self) -> usize {
        self.boundaries.len().saturating_sub(1)
    }
}

/// Per-class PSDS and its operating curve.
#[derive(Debug, Clone, PartialEq)]
pub struct ClassPsds {
    /// Class identifier.
    pub class_id: u32,
    /// Reference events for the class.
    pub n_reference: u64,
    /// Total reference duration in seconds (the cross-trigger denominator).
    pub reference_duration: f64,
    /// Area under this class's PSD-ROC divided by `max_efpr`.
    pub psds: f64,
    /// Operating points of the truncated envelope (ascending eFPR).
    pub efpr: Vec<f64>,
    /// True-positive rates at `efpr`.
    pub tpr: Vec<f64>,
}

/// PSDS result.
#[derive(Debug, Clone, PartialEq)]
pub struct PsdsResult {
    /// Macro PSDS after the `alpha_st` penalty.
    pub psds: f64,
    /// Effective false-positive rates of the macro curve.
    pub efpr: Vec<f64>,
    /// Effective true-positive rates of the macro curve.
    pub tpr: Vec<f64>,
    /// Per-class results, sorted by class id.
    pub classes: Vec<ClassPsds>,
    /// Total audio duration of the evaluated recordings, in seconds.
    pub dataset_duration: f64,
    /// Configuration used.
    pub config: PsdsConfig,
}

#[derive(Debug, Clone, Default, PartialEq)]
struct Stats {
    tps: i64,
    fps: i64,
    cts: Vec<i64>,
}

impl Stats {
    fn subtract(&self, other: &Stats) -> Stats {
        Stats {
            tps: self.tps - other.tps,
            fps: self.fps - other.fps,
            cts: self
                .cts
                .iter()
                .zip(&other.cts)
                .map(|(left, right)| left - right)
                .collect(),
        }
    }

    fn is_zero(&self) -> bool {
        self.tps == 0 && self.fps == 0 && self.cts.iter().all(|count| *count == 0)
    }

    fn add_assign(&mut self, other: &Stats) {
        self.tps += other.tps;
        self.fps += other.fps;
        for (left, right) in self.cts.iter_mut().zip(&other.cts) {
            *left += right;
        }
    }
}

fn round_to(value: f64, decimals: u32) -> f64 {
    // numpy.round is round-half-to-even on `value * 10^decimals`.
    let factor = 10_f64.powi(decimals as i32);
    (value * factor).round_ties_even() / factor
}

fn intersection(left: (f64, f64), right: (f64, f64)) -> f64 {
    let start = left.0.max(right.0);
    let end = left.1.min(right.1);
    (end - start).max(0.0)
}

/// DTC-relevant detections and the per-reference GTC outcome at one threshold.
fn criterion_stats(
    detections: &[(f64, f64)],
    references: &[(f64, f64)],
    other_references: &[Vec<(f64, f64)>],
    config: &PsdsConfig,
) -> Stats {
    let decimals = config.time_decimals;
    let mut relevant = vec![false; detections.len()];
    for (index, detection) in detections.iter().enumerate() {
        let length = detection.1 - detection.0;
        let covered: f64 = references
            .iter()
            .map(|reference| intersection(*detection, *reference))
            .sum();
        relevant[index] =
            round_to(covered, decimals) >= round_to(config.dtc_threshold * length, decimals);
    }

    // GTC: only DTC-relevant detections contribute to a reference.
    let mut tps = 0_i64;
    for reference in references {
        let length = reference.1 - reference.0;
        let covered: f64 = detections
            .iter()
            .zip(&relevant)
            .filter(|(_, is_relevant)| **is_relevant)
            .map(|(detection, _)| intersection(*detection, *reference))
            .sum();
        if round_to(covered, decimals) >= round_to(config.gtc_threshold * length, decimals) {
            tps += 1;
        }
    }

    let mut cts = vec![0_i64; other_references.len()];
    if let Some(cttc_threshold) = config.cttc_threshold {
        for (index, detection) in detections.iter().enumerate() {
            if relevant[index] {
                continue;
            }
            let length = detection.1 - detection.0;
            for (other_index, references) in other_references.iter().enumerate() {
                let covered: f64 = references
                    .iter()
                    .map(|reference| intersection(*detection, *reference))
                    .sum();
                if round_to(covered, decimals) >= round_to(cttc_threshold * length, decimals) {
                    cts[other_index] += 1;
                }
            }
        }
    }

    Stats {
        tps,
        fps: detections.len() as i64 - relevant.iter().filter(|flag| **flag).count() as i64,
        cts,
    }
}

/// Maximal runs of frames with `score >= threshold`.
fn detections_at(scores: &[f64], boundaries: &[f64], threshold: f64) -> Vec<(f64, f64)> {
    let mut detections = Vec::new();
    let mut start: Option<usize> = None;
    for (index, score) in scores.iter().enumerate() {
        if *score >= threshold {
            if start.is_none() {
                start = Some(index);
            }
        } else if let Some(start) = start.take() {
            detections.push((boundaries[start], boundaries[index]));
        }
    }
    if let Some(start) = start {
        detections.push((boundaries[start], boundaries[scores.len()]));
    }
    detections
}

fn unique_sorted(values: &mut [f64]) -> Vec<f64> {
    values.sort_by(f64::total_cmp);
    let mut unique: Vec<f64> = Vec::with_capacity(values.len());
    for value in values.iter() {
        if unique.last().is_none_or(|last| *last != *value) {
            unique.push(*value);
        }
    }
    unique
}

/// Area under a staircase curve, left endpoints, truncated at `max_x`.
fn staircase_auc(tpr: &[f64], efpr: &[f64], max_x: f64) -> f64 {
    if tpr.is_empty() {
        return 0.0;
    }
    let mut points: Vec<(f64, f64)> = efpr.iter().copied().zip(tpr.iter().copied()).collect();
    points.sort_by(|left, right| left.0.total_cmp(&right.0));
    points.retain(|(x, _)| *x <= max_x);
    if points.is_empty() {
        return 0.0;
    }
    let mut area = 0.0;
    for index in 0..points.len() {
        let width = points.get(index + 1).map(|(x, _)| *x).unwrap_or(max_x) - points[index].0;
        area += points[index].1 * width;
    }
    area / max_x
}

fn step_value(efpr: &[f64], tpr: &[f64], x: f64) -> f64 {
    if efpr.is_empty() {
        return 0.0;
    }
    // Right-continuous step: the value at the last knot with `knot <= x`.
    match efpr.partition_point(|knot| *knot <= x) {
        0 => 0.0,
        index => tpr[index - 1],
    }
}

/// Turn per-threshold deltas into the operating-point series of one class.
fn accumulate_operating_points(
    mut deltas: Vec<(f64, Stats)>,
    n_other_classes: usize,
) -> Vec<(f64, Stats)> {
    deltas.sort_by(|left, right| left.0.total_cmp(&right.0));
    let mut accumulated: Vec<(f64, Stats)> = Vec::new();
    for (score, stats) in deltas {
        match accumulated.last_mut() {
            Some((last_score, accumulated_stats)) if *last_score == score => {
                accumulated_stats.add_assign(&stats);
            }
            _ => accumulated.push((score, stats)),
        }
    }

    let empty = || Stats {
        tps: 0,
        fps: 0,
        cts: vec![0; n_other_classes],
    };
    let mut running = empty();
    let mut operating_points: Vec<(f64, Stats)> = Vec::with_capacity(accumulated.len() + 1);
    for (score, stats) in accumulated.iter().rev() {
        running.add_assign(stats);
        operating_points.push((*score, running.clone()));
    }
    operating_points.reverse();
    // The "no detections" operating point.
    operating_points.push((f64::INFINITY, empty()));
    operating_points
}

/// Compute PSDS and its per-class curves.
pub fn psds(
    references: &[Event],
    tracks: &[ScoreTrack],
    recordings: &[Recording],
    config: &PsdsConfig,
) -> Result<PsdsResult, ValidationError> {
    config.validate()?;
    validate_recordings(recordings)?;
    validate_events(references, Some(recordings))?;

    let durations: BTreeMap<u32, f64> = recordings
        .iter()
        .map(|recording| (recording.recording_id, recording.duration))
        .collect();

    let mut seen_recordings = BTreeSet::new();
    for track in tracks {
        if !seen_recordings.insert(track.recording_id) {
            return Err(ValidationError::DuplicateScoreTrack {
                recording_id: track.recording_id,
            });
        }
        if !durations.contains_key(&track.recording_id) {
            return Err(ValidationError::UnknownRecording {
                recording_id: track.recording_id,
                class_id: 0,
            });
        }
        if track.class_ids.is_empty() {
            return Err(ValidationError::InvalidScoreTrack {
                recording_id: track.recording_id,
                reason: "no class columns",
            });
        }
        let mut unique_classes = BTreeSet::new();
        for class_id in &track.class_ids {
            if !unique_classes.insert(*class_id) {
                return Err(ValidationError::InvalidScoreTrack {
                    recording_id: track.recording_id,
                    reason: "duplicate class column",
                });
            }
        }
        if track.boundaries.len() < 2 {
            return Err(ValidationError::InvalidScoreTrack {
                recording_id: track.recording_id,
                reason: "fewer than two frame boundaries",
            });
        }
        for pair in track.boundaries.windows(2) {
            if !(pair[0].is_finite() && pair[1].is_finite()) || pair[1] <= pair[0] {
                return Err(ValidationError::InvalidScoreTrack {
                    recording_id: track.recording_id,
                    reason: "frame boundaries must increase",
                });
            }
        }
        let duration = durations[&track.recording_id];
        if track.boundaries[0] < 0.0 || *track.boundaries.last().unwrap() > duration {
            return Err(ValidationError::InvalidScoreTrack {
                recording_id: track.recording_id,
                reason: "frame boundaries outside the recording",
            });
        }
        let expected = track.n_frames() * track.class_ids.len();
        if track.scores.len() != expected {
            return Err(ValidationError::InvalidScoreTrack {
                recording_id: track.recording_id,
                reason: "score matrix has the wrong number of values",
            });
        }
        if track.scores.iter().any(|score| !score.is_finite()) {
            return Err(ValidationError::InvalidScoreTrack {
                recording_id: track.recording_id,
                reason: "non-finite score",
            });
        }
    }

    // Classes must match exactly on both sides: metrics over an unscored class
    // and scores without references are both meaningless for PSDS.
    let score_classes: BTreeSet<u32> = tracks
        .iter()
        .flat_map(|track| track.class_ids.iter().copied())
        .collect();
    let reference_classes: BTreeSet<u32> = references.iter().map(|event| event.class_id).collect();
    if score_classes != reference_classes {
        return Err(ValidationError::ClassVocabularyMismatch);
    }
    let classes: Vec<u32> = score_classes.iter().copied().collect();
    let class_index: BTreeMap<u32, usize> = classes
        .iter()
        .enumerate()
        .map(|(index, class_id)| (*class_id, index))
        .collect();

    // Reference events per (recording, class) and class totals.
    let mut references_by_recording: BTreeMap<u32, Vec<Vec<(f64, f64)>>> =
        std::collections::BTreeMap::new();
    let mut reference_count = vec![0_u64; classes.len()];
    let mut reference_duration = vec![0.0_f64; classes.len()];
    for event in references {
        let index = class_index[&event.class_id];
        references_by_recording
            .entry(event.recording_id)
            .or_insert_with(|| vec![Vec::new(); classes.len()])[index]
            .push((event.onset, event.offset));
        reference_count[index] += 1;
        reference_duration[index] += event.offset - event.onset;
    }

    let dataset_duration: f64 = recordings.iter().map(|recording| recording.duration).sum();
    if dataset_duration <= 0.0 {
        return Err(ValidationError::InvalidParameter {
            field: "dataset_duration",
            value: dataset_duration,
        });
    }

    // Deltas of the intermediate statistics w.r.t. the threshold, per class.
    let mut deltas: Vec<Vec<(f64, Stats)>> = vec![Vec::new(); classes.len()];
    for track in tracks {
        let frames = track.n_frames();
        let n_classes = track.class_ids.len();
        let empty: Vec<Vec<(f64, f64)>> = vec![Vec::new(); classes.len()];
        let recording_references = references_by_recording
            .get(&track.recording_id)
            .unwrap_or(&empty);

        for (column, class_id) in track.class_ids.iter().enumerate() {
            let index = class_index[class_id];
            let scores: Vec<f64> = (0..frames)
                .map(|frame| track.scores[frame * n_classes + column] as f64)
                .collect();
            let mut thresholds = scores.clone();
            let thresholds = unique_sorted(&mut thresholds);

            let other_references: Vec<Vec<(f64, f64)>> = classes
                .iter()
                .enumerate()
                .filter(|(other_index, _)| *other_index != index)
                .map(|(other_index, _)| recording_references[other_index].clone())
                .collect();

            let mut per_threshold: Vec<Stats> = Vec::with_capacity(thresholds.len());
            for threshold in &thresholds {
                let detections = detections_at(&scores, &track.boundaries, *threshold);
                per_threshold.push(criterion_stats(
                    &detections,
                    &recording_references[index],
                    &other_references,
                    config,
                ));
            }

            // delta_i = stats(s_i) - stats(s_{i+1}); the last one is vs. zero.
            for (position, threshold) in thresholds.iter().enumerate() {
                let next = per_threshold
                    .get(position + 1)
                    .cloned()
                    .unwrap_or_else(|| Stats {
                        tps: 0,
                        fps: 0,
                        cts: vec![0; per_threshold[0].cts.len()],
                    });
                let delta = per_threshold[position].subtract(&next);
                if !delta.is_zero() {
                    deltas[index].push((*threshold, delta));
                }
            }
        }
    }

    // Accumulate equal change-point scores per class, then reverse cumsum.
    let operating_points: Vec<Vec<(f64, Stats)>> = deltas
        .into_iter()
        .map(|class_deltas| {
            accumulate_operating_points(class_deltas, classes.len().saturating_sub(1))
        })
        .collect();

    let unit = config.unit.seconds_per_unit();
    let mut class_results: Vec<ClassPsds> = Vec::with_capacity(classes.len());
    for (class_index_value, class_id) in classes.iter().enumerate() {
        let n_reference = reference_count[class_index_value];
        if n_reference == 0 {
            return Err(ValidationError::ClassWithoutReferences {
                class_id: *class_id,
            });
        }

        let mut points: Vec<(f64, f64)> = operating_points[class_index_value]
            .iter()
            .map(|(_, stats)| {
                let tpr = stats.tps as f64 / n_reference as f64;
                let mut efpr = stats.fps as f64 / dataset_duration;
                if config.alpha_ct > 0.0 {
                    let mut cross_rates = Vec::with_capacity(stats.cts.len());
                    for (other_index, count) in stats.cts.iter().enumerate() {
                        let other = if other_index < class_index_value {
                            other_index
                        } else {
                            other_index + 1
                        };
                        cross_rates.push(*count as f64 / reference_duration[other].max(1e-12));
                    }
                    if !cross_rates.is_empty() {
                        let mean = cross_rates.iter().sum::<f64>() / cross_rates.len() as f64;
                        efpr += config.alpha_ct * mean;
                    }
                }
                (efpr * unit, tpr)
            })
            .collect();
        // (efpr, tpr): the raw PSDS coordinates are eFPR-first.

        // Pareto frontier: ascending eFPR, keep strictly increasing TPR.
        points.sort_by(|left, right| left.0.total_cmp(&right.0).then(left.1.total_cmp(&right.1)));
        let mut frontier: Vec<(f64, f64)> = Vec::with_capacity(points.len());
        let mut best = f64::NEG_INFINITY;
        for point in points {
            if point.1 > best {
                best = point.1;
                frontier.push(point);
            }
        }
        // Equal eFPR: keep the highest TPR (the last of the run).
        let mut deduped: Vec<(f64, f64)> = Vec::with_capacity(frontier.len());
        for point in frontier {
            match deduped.last_mut() {
                Some(last) if last.0 == point.0 => *last = point,
                _ => deduped.push(point),
            }
        }
        deduped.retain(|(efpr, _)| *efpr <= config.max_efpr);

        let efpr: Vec<f64> = deduped.iter().map(|(efpr, _)| *efpr).collect();
        let tpr: Vec<f64> = deduped.iter().map(|(_, tpr)| *tpr).collect();
        let score = staircase_auc(&tpr, &efpr, config.max_efpr);
        class_results.push(ClassPsds {
            class_id: *class_id,
            n_reference,
            reference_duration: reference_duration[class_index_value],
            psds: score,
            efpr,
            tpr,
        });
    }

    // Macro aggregation on the union of the per-class eFPR grids.
    let mut grid: Vec<f64> = class_results
        .iter()
        .flat_map(|class| class.efpr.iter().copied())
        .collect();
    grid.sort_by(f64::total_cmp);
    grid.dedup();

    let mut interpolated: Vec<Vec<f64>> = Vec::with_capacity(class_results.len());
    for class in &class_results {
        interpolated.push(
            grid.iter()
                .map(|x| step_value(&class.efpr, &class.tpr, *x))
                .collect(),
        );
    }

    let n_classes = class_results.len() as f64;
    let mut effective_tpr: Vec<f64> = Vec::with_capacity(grid.len());
    for column in 0..grid.len() {
        let values: Vec<f64> = interpolated.iter().map(|series| series[column]).collect();
        let mean = values.iter().sum::<f64>() / n_classes;
        let variance = values
            .iter()
            .map(|value| (value - mean).powi(2))
            .sum::<f64>()
            / n_classes;
        let penalised = mean - config.alpha_st * variance.sqrt();
        effective_tpr.push(penalised.max(0.0));
    }
    if let Some(last) = effective_tpr.last().copied() {
        effective_tpr.push(last);
        grid.push(config.max_efpr);
    }

    let score = staircase_auc(&effective_tpr, &grid, config.max_efpr);

    Ok(PsdsResult {
        psds: score,
        efpr: grid,
        tpr: effective_tpr,
        classes: class_results,
        dataset_duration,
        config: *config,
    })
}
