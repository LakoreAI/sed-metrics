//! Binary classification on an explicitly aligned frame grid.

use crate::{
    Event, Recording,
    validation::{validate_events, validate_recordings},
};

/// Map reference events to a single recording/class grid using positive overlap.
pub fn labels_from_events(
    references: &[Event],
    recording: Recording,
    class_id: u32,
    boundaries: &[f64],
) -> Result<Vec<bool>, String> {
    validate_recordings(&[recording]).map_err(|error| error.to_string())?;
    validate_events(references, None).map_err(|error| error.to_string())?;
    if boundaries.len() < 2
        || boundaries[0] != 0.0
        || boundaries[boundaries.len() - 1] != recording.duration
        || boundaries
            .windows(2)
            .any(|p| !p[0].is_finite() || !p[1].is_finite() || p[0] >= p[1])
    {
        return Err("boundaries must strictly increase from zero to recording duration".into());
    }
    if references.iter().any(|event| {
        event.recording_id == recording.recording_id && event.offset > recording.duration
    }) {
        return Err("reference event exceeds recording duration".into());
    }
    Ok(boundaries
        .windows(2)
        .map(|frame| {
            references.iter().any(|event| {
                event.recording_id == recording.recording_id
                    && event.class_id == class_id
                    && event.onset < frame[1]
                    && frame[0] < event.offset
            })
        })
        .collect())
}

/// Sufficient statistics and ranking metrics for one class.
#[derive(Debug, Clone, PartialEq)]
pub struct FrameResult {
    /// Weighted true positives.
    pub tp: f64,
    /// Weighted false positives.
    pub fp: f64,
    /// Weighted false negatives.
    pub fn_: f64,
    /// Weighted true negatives.
    pub tn: f64,
    /// Precision, undefined without positive predictions.
    pub precision: Option<f64>,
    /// Recall, undefined without positive references.
    pub recall: Option<f64>,
    /// F1, undefined when both reference and predictions are empty.
    pub f1: Option<f64>,
    /// Non-interpolated average precision, undefined without positive references.
    pub average_precision: Option<f64>,
    /// AUROC, undefined without positive and negative references.
    pub auroc: Option<f64>,
}

fn ratio(a: f64, b: f64) -> Option<f64> {
    if b > 0.0 { Some(a / b) } else { None }
}

/// Evaluate one class. Weights must be finite and positive; threshold equality is active.
pub fn frame_metrics(
    labels: &[bool],
    scores: &[f64],
    weights: &[f64],
    threshold: f64,
) -> Result<FrameResult, &'static str> {
    if labels.len() != scores.len() || labels.len() != weights.len() {
        return Err("labels, scores and weights must have equal lengths");
    }
    if !threshold.is_finite() || scores.iter().any(|s| !s.is_finite()) {
        return Err("threshold and scores must be finite");
    }
    if weights.iter().any(|w| !w.is_finite() || *w <= 0.0) {
        return Err("weights must be finite and positive");
    }
    let (mut tp, mut fp, mut fn_, mut tn) = (0.0, 0.0, 0.0, 0.0);
    let mut ranked: Vec<(f64, bool, f64)> = Vec::with_capacity(labels.len());
    for ((&label, &score), &weight) in labels.iter().zip(scores).zip(weights) {
        match (label, score >= threshold) {
            (true, true) => tp += weight,
            (false, true) => fp += weight,
            (true, false) => fn_ += weight,
            (false, false) => tn += weight,
        }
        ranked.push((score, label, weight));
    }
    let positives = tp + fn_;
    let negatives = fp + tn;
    if !positives.is_finite() || !negatives.is_finite() || !(positives + negatives).is_finite() {
        return Err("total weight must be finite");
    }
    ranked.sort_by(|a, b| b.0.total_cmp(&a.0));
    let (mut hit, mut false_hit, mut ap, mut auc, mut index) = (0.0, 0.0, 0.0, 0.0, 0);
    while index < ranked.len() {
        let value = ranked[index].0;
        let (mut pos, mut neg) = (0.0, 0.0);
        while index < ranked.len() && ranked[index].0 == value {
            if ranked[index].1 {
                pos += ranked[index].2;
            } else {
                neg += ranked[index].2;
            }
            index += 1;
        }
        hit += pos;
        false_hit += neg;
        if positives > 0.0 {
            ap += pos / positives * hit / (hit + false_hit);
        }
        if positives > 0.0 && negatives > 0.0 {
            auc += (neg / negatives) * ((hit - pos / 2.0) / positives);
        }
    }
    Ok(FrameResult {
        tp,
        fp,
        fn_,
        tn,
        precision: ratio(tp, tp + fp),
        recall: ratio(tp, positives),
        f1: ratio(2.0 * tp, 2.0 * tp + fp + fn_),
        average_precision: (positives > 0.0).then_some(ap),
        auroc: (positives > 0.0 && negatives > 0.0).then_some(auc),
    })
}
