//! Collar-based event detection metrics (precision, recall, F1, counts).
//!
//! Specification: `docs/metrics/event_f1.md`.

use std::collections::BTreeMap;

use crate::matching::{CollarConfig, maximum_matching};
use crate::types::{Event, Recording};
use crate::validation::{ValidationError, validate_events, validate_recordings};

/// How per-class statistics are combined into the reported totals.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Averaging {
    /// Pool counts over all classes, then compute the metric (`TP`-weighted).
    Micro,
    /// Compute the metric per class, then take the unweighted mean over the
    /// classes where that metric is defined.
    Macro,
}

impl Averaging {
    /// Stable lowercase name, matching the Python API.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Micro => "micro",
            Self::Macro => "macro",
        }
    }
}

/// Configuration for collar-based event F1.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct EventF1Config {
    /// Collar rules.
    pub collar: CollarConfig,
    /// Class aggregation.
    pub average: Averaging,
}

impl Default for EventF1Config {
    /// The documented `dcase2016` profile: 200 ms / 20 % collars, micro F1.
    fn default() -> Self {
        Self {
            collar: CollarConfig::default(),
            average: Averaging::Micro,
        }
    }
}

impl EventF1Config {
    /// Check collar parameters.
    pub fn validate(&self) -> Result<(), ValidationError> {
        self.collar.validate()
    }
}

/// Per-class result. Counts are always reported, even when a ratio is undefined.
#[derive(Debug, Clone, PartialEq)]
pub struct ClassEventF1 {
    /// Class identifier.
    pub class_id: u32,
    /// Number of reference events.
    pub n_reference: u64,
    /// Number of predicted events.
    pub n_predicted: u64,
    /// Number of matched reference/prediction pairs.
    pub n_correct: u64,
    /// Predictions without a reference partner.
    pub n_insertions: u64,
    /// References without a prediction partner.
    pub n_deletions: u64,
    /// `n_correct / n_predicted`, `None` when there are no predictions.
    pub precision: Option<f64>,
    /// `n_correct / n_reference`, `None` when there are no references.
    pub recall: Option<f64>,
    /// Harmonic-mean style F1 from counts, `None` when all counts are zero.
    pub f1: Option<f64>,
    /// Mean absolute onset error over matched pairs, seconds.
    pub mean_onset_error: Option<f64>,
    /// Mean absolute offset error over matched pairs, seconds.
    pub mean_offset_error: Option<f64>,
}

/// Aggregate result.
#[derive(Debug, Clone, PartialEq)]
pub struct EventF1Result {
    /// Aggregation that produced the top-level ratios.
    pub average: Averaging,
    /// Total reference events.
    pub n_reference: u64,
    /// Total predicted events.
    pub n_predicted: u64,
    /// Total matched pairs.
    pub n_correct: u64,
    /// Total insertions.
    pub n_insertions: u64,
    /// Total deletions.
    pub n_deletions: u64,
    /// Precision under the configured averaging; `None` when undefined.
    pub precision: Option<f64>,
    /// Recall under the configured averaging; `None` when undefined.
    pub recall: Option<f64>,
    /// F1 under the configured averaging; `None` when undefined.
    pub f1: Option<f64>,
    /// Mean absolute onset error over all matched pairs, seconds.
    pub mean_onset_error: Option<f64>,
    /// Mean absolute offset error over all matched pairs, seconds.
    pub mean_offset_error: Option<f64>,
    /// Number of distinct classes present in references or predictions.
    pub n_classes: u64,
    /// Per-class statistics, sorted by class id.
    pub classes: Vec<ClassEventF1>,
    /// Configuration used, echoed for auditability.
    pub config: EventF1Config,
}

#[derive(Debug, Default, Clone, Copy)]
struct Tally {
    reference: u64,
    predicted: u64,
    correct: u64,
    onset_error: f64,
    offset_error: f64,
}

impl Tally {
    fn add_match(&mut self, reference: &Event, prediction: &Event) {
        self.correct += 1;
        self.onset_error += (prediction.onset - reference.onset).abs();
        self.offset_error += (prediction.offset - reference.offset).abs();
    }

    fn insertions(&self) -> u64 {
        self.predicted - self.correct
    }

    fn deletions(&self) -> u64 {
        self.reference - self.correct
    }

    fn precision(&self) -> Option<f64> {
        ratio(self.correct, self.predicted)
    }

    fn recall(&self) -> Option<f64> {
        ratio(self.correct, self.reference)
    }

    fn f1(&self) -> Option<f64> {
        let denominator = 2 * self.correct + self.insertions() + self.deletions();
        ratio(2 * self.correct, denominator)
    }

    fn mean_onset_error(&self) -> Option<f64> {
        ratio_f64(self.onset_error, self.correct)
    }

    fn mean_offset_error(&self) -> Option<f64> {
        ratio_f64(self.offset_error, self.correct)
    }

    fn add(&mut self, other: &Tally) {
        self.reference += other.reference;
        self.predicted += other.predicted;
        self.correct += other.correct;
        self.onset_error += other.onset_error;
        self.offset_error += other.offset_error;
    }
}

fn ratio(numerator: u64, denominator: u64) -> Option<f64> {
    if denominator == 0 {
        None
    } else {
        Some(numerator as f64 / denominator as f64)
    }
}

fn ratio_f64(numerator: f64, denominator: u64) -> Option<f64> {
    if denominator == 0 {
        None
    } else {
        Some(numerator / denominator as f64)
    }
}

fn macro_mean<F>(classes: &[ClassEventF1], select: F) -> Option<f64>
where
    F: Fn(&ClassEventF1) -> Option<f64>,
{
    let mut sum = 0.0;
    let mut count = 0_u64;
    for class in classes {
        if let Some(value) = select(class) {
            sum += value;
            count += 1;
        }
    }
    ratio_f64(sum, count)
}

fn sort_events(events: &mut [Event]) {
    events.sort_by(|left, right| {
        left.onset
            .total_cmp(&right.onset)
            .then(left.offset.total_cmp(&right.offset))
    });
}

/// Compute collar-based event precision, recall and F1.
///
/// One-to-one maximum-cardinality matching is computed independently per
/// `(recording, class)` group; class totals are then pooled over recordings.
///
/// A prediction may match at most one reference, and a reference at most one
/// prediction. Unmatched predictions count as insertions, unmatched references
/// as deletions.
///
/// # Undefined values
///
/// Ratios with a zero denominator are `None`, not `NaN` and not zero:
/// precision needs at least one prediction, recall at least one reference, and
/// F1 at least one reference or prediction. Under [`Averaging::Macro`] each of
/// the three ratios is the unweighted mean over the classes where *that* ratio
/// is defined; the support can therefore differ between precision, recall and
/// F1, and macro F1 is not the harmonic mean of macro precision and macro recall.
pub fn event_f1(
    references: &[Event],
    predictions: &[Event],
    config: &EventF1Config,
    recordings: Option<&[Recording]>,
) -> Result<EventF1Result, ValidationError> {
    config.validate()?;
    if let Some(recordings) = recordings {
        validate_recordings(recordings)?;
    }
    validate_events(references, recordings)?;
    validate_events(predictions, recordings)?;

    let mut groups: BTreeMap<(u32, u32), (Vec<Event>, Vec<Event>)> = BTreeMap::new();
    for event in references {
        groups
            .entry((event.recording_id, event.class_id))
            .or_default()
            .0
            .push(*event);
    }
    for event in predictions {
        groups
            .entry((event.recording_id, event.class_id))
            .or_default()
            .1
            .push(*event);
    }

    let mut per_class: BTreeMap<u32, Tally> = BTreeMap::new();
    for ((_recording_id, class_id), (mut group_references, mut group_predictions)) in groups {
        sort_events(&mut group_references);
        sort_events(&mut group_predictions);

        let tally = per_class.entry(class_id).or_default();
        tally.reference += group_references.len() as u64;
        tally.predicted += group_predictions.len() as u64;

        let pairs = maximum_matching(&group_references, &group_predictions, &config.collar);
        let tally = per_class
            .get_mut(&class_id)
            .expect("class entry was inserted above");
        for (reference_index, prediction_index) in pairs {
            tally.add_match(
                &group_references[reference_index],
                &group_predictions[prediction_index],
            );
        }
    }

    let mut total = Tally::default();
    for tally in per_class.values() {
        total.add(tally);
    }

    let classes: Vec<ClassEventF1> = per_class
        .iter()
        .map(|(class_id, tally)| ClassEventF1 {
            class_id: *class_id,
            n_reference: tally.reference,
            n_predicted: tally.predicted,
            n_correct: tally.correct,
            n_insertions: tally.insertions(),
            n_deletions: tally.deletions(),
            precision: tally.precision(),
            recall: tally.recall(),
            f1: tally.f1(),
            mean_onset_error: tally.mean_onset_error(),
            mean_offset_error: tally.mean_offset_error(),
        })
        .collect();

    let (precision, recall, f1) = match config.average {
        Averaging::Micro => (total.precision(), total.recall(), total.f1()),
        Averaging::Macro => (
            macro_mean(&classes, |class| class.precision),
            macro_mean(&classes, |class| class.recall),
            macro_mean(&classes, |class| class.f1),
        ),
    };

    Ok(EventF1Result {
        average: config.average,
        n_reference: total.reference,
        n_predicted: total.predicted,
        n_correct: total.correct,
        n_insertions: total.insertions(),
        n_deletions: total.deletions(),
        precision,
        recall,
        f1,
        mean_onset_error: total.mean_onset_error(),
        mean_offset_error: total.mean_offset_error(),
        n_classes: classes.len() as u64,
        classes,
        config: *config,
    })
}
