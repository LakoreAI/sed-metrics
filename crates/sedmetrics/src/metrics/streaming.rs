//! Experimental immutable CREATE alert evaluation.
use crate::{
    Event, Recording,
    validation::{validate_events, validate_recordings},
};
use std::collections::{BTreeMap, BTreeSet};

/// A CREATE alert on a recording clock.
#[derive(Debug, Clone)]
pub struct CreateAlert {
    /// Recording identity.
    pub recording_id: u32,
    /// Unique alert identity within recording.
    pub alert_id: u64,
    /// Class identity.
    pub class_id: u32,
    /// Decision availability time in seconds.
    pub emitted_at: f64,
    /// Latest audio available at emission.
    pub audio_available_until: f64,
    /// Latest audio actually consumed, when known.
    pub latest_audio_used: Option<f64>,
}

/// Result for fixed assignment, including censored counts and exposure.
#[derive(Debug, Clone)]
pub struct StreamingResult {
    /// Total references.
    pub n_reference: usize,
    /// References whose entire matching window was observed.
    pub n_observed: usize,
    /// References with windows truncated by clip end.
    pub n_censored: usize,
    /// Matches to fully observed references.
    pub n_matched: usize,
    /// Matches to censored references.
    pub n_censored_matched: usize,
    /// Unmatched CREATE alerts.
    pub n_false_alerts: usize,
    /// Total observed audio duration, seconds.
    pub exposure_seconds: f64,
    /// Recall at each requested deadline.
    pub deadline_recall: Vec<Option<f64>>,
    /// Normalized area under deadline recall.
    pub audr: Option<f64>,
    /// Unmatched alerts per hour.
    pub false_alerts_per_hour: Option<f64>,
    /// Matched delays for the fully observed cohort.
    pub delays: Vec<f64>,
    /// Matched `(reference index, alert index)` pairs including censored events.
    pub matches: Vec<(usize, usize)>,
}

#[derive(Clone, Copy, Default)]
struct Cell {
    count: usize,
    delay: f64,
    step: u8,
}

/// Maximum-cardinality, minimum-total-delay fixed matching, then cohort metrics.
pub fn evaluate_streaming(
    references: &[Event],
    alerts: &[CreateAlert],
    recordings: &[Recording],
    class_ids: &[u32],
    window: f64,
    deadlines: &[f64],
    horizon: f64,
) -> Result<StreamingResult, String> {
    validate_recordings(recordings).map_err(|e| e.to_string())?;
    validate_events(references, Some(recordings)).map_err(|e| e.to_string())?;
    let vocabulary: BTreeSet<u32> = class_ids.iter().copied().collect();
    if vocabulary.is_empty() || vocabulary.len() != class_ids.len() {
        return Err("class vocabulary must be nonempty and unique".into());
    }
    if references
        .iter()
        .any(|event| !vocabulary.contains(&event.class_id))
        || alerts
            .iter()
            .any(|alert| !vocabulary.contains(&alert.class_id))
    {
        return Err("reference or alert contains an unknown class".into());
    }
    if !window.is_finite()
        || window <= 0.0
        || !horizon.is_finite()
        || horizon <= 0.0
        || deadlines.iter().any(|v| !v.is_finite() || *v < 0.0)
    {
        return Err(
            "window and horizon must be positive and deadlines nonnegative and finite".into(),
        );
    }
    let durations: BTreeMap<u32, f64> = recordings
        .iter()
        .map(|r| (r.recording_id, r.duration))
        .collect();
    let mut ids = BTreeSet::new();
    let mut last = BTreeMap::new();
    for a in alerts {
        let duration = *durations
            .get(&a.recording_id)
            .ok_or("alert references an unknown recording")?;
        if !a.emitted_at.is_finite()
            || a.emitted_at < 0.0
            || a.emitted_at > duration
            || !a.audio_available_until.is_finite()
            || a.audio_available_until < 0.0
            || a.audio_available_until > duration
            || a.audio_available_until > a.emitted_at
        {
            return Err("invalid alert emission or availability time".into());
        }
        if a.latest_audio_used
            .is_some_and(|x| !x.is_finite() || x < 0.0 || x > a.audio_available_until)
        {
            return Err("invalid latest_audio_used".into());
        }
        if !ids.insert((a.recording_id, a.alert_id)) {
            return Err("duplicate alert identity".into());
        }
        if last
            .insert(a.recording_id, a.emitted_at)
            .is_some_and(|t| t > a.emitted_at)
        {
            return Err("alerts must be ordered by emission within each recording".into());
        }
    }
    let nr = references.len();
    let na = alerts.len();
    let mut groups: BTreeMap<(u32, u32), (Vec<usize>, Vec<usize>)> = BTreeMap::new();
    for (i, r) in references.iter().enumerate() {
        groups
            .entry((r.recording_id, r.class_id))
            .or_default()
            .0
            .push(i);
    }
    for (j, a) in alerts.iter().enumerate() {
        groups
            .entry((a.recording_id, a.class_id))
            .or_default()
            .1
            .push(j);
    }
    let mut matches = Vec::new();
    for (_, (mut refs, mut preds)) in groups {
        refs.sort_by(|&a, &b| {
            references[a]
                .onset
                .total_cmp(&references[b].onset)
                .then(a.cmp(&b))
        });
        preds.sort_by(|&a, &b| {
            alerts[a]
                .emitted_at
                .total_cmp(&alerts[b].emitted_at)
                .then(a.cmp(&b))
        });
        let width = preds.len() + 1;
        let size = (refs.len() + 1)
            .checked_mul(width)
            .ok_or("matching table too large")?;
        let mut table = vec![Cell::default(); size];
        for i in 0..=refs.len() {
            for j in 0..=preds.len() {
                if i == 0 && j == 0 {
                    continue;
                }
                let mut best = Cell {
                    count: 0,
                    delay: f64::INFINITY,
                    step: 0,
                };
                let mut consider = |candidate: Cell, step| {
                    if candidate.count > best.count
                        || (candidate.count == best.count && candidate.delay < best.delay)
                    {
                        best = Cell { step, ..candidate };
                    }
                };
                if i > 0 {
                    consider(table[(i - 1) * width + j], 1);
                }
                if j > 0 {
                    consider(table[i * width + j - 1], 2);
                }
                if i > 0 && j > 0 {
                    let delay = alerts[preds[j - 1]].emitted_at - references[refs[i - 1]].onset;
                    if delay >= 0.0 && delay <= window {
                        let prev = table[(i - 1) * width + j - 1];
                        consider(
                            Cell {
                                count: prev.count + 1,
                                delay: prev.delay + delay,
                                step: 0,
                            },
                            3,
                        );
                    }
                }
                table[i * width + j] = best;
            }
        }
        let (mut i, mut j) = (refs.len(), preds.len());
        while i > 0 || j > 0 {
            match table[i * width + j].step {
                1 => i -= 1,
                2 => j -= 1,
                3 => {
                    matches.push((refs[i - 1], preds[j - 1]));
                    i -= 1;
                    j -= 1;
                }
                _ => return Err("invalid matching table".into()),
            }
        }
    }
    matches.sort_unstable();
    let mut delays = Vec::new();
    let mut censored = 0;
    let mut censored_matched = 0;
    let mut matched_total = 0;
    for (i, r) in references.iter().enumerate() {
        let truncated = r.onset + window > durations[&r.recording_id];
        if truncated {
            censored += 1;
        }
        for &(_, j) in matches.iter().filter(|(reference, _)| *reference == i) {
            matched_total += 1;
            if truncated {
                censored_matched += 1;
            } else {
                delays.push(alerts[j].emitted_at - r.onset);
            }
        }
    }
    let observed = nr - censored;
    let exposure: f64 = recordings.iter().map(|r| r.duration).sum();
    if !exposure.is_finite() {
        return Err("total exposure must be finite".into());
    }
    let recall = deadlines
        .iter()
        .map(|t| {
            (observed > 0)
                .then(|| delays.iter().filter(|d| **d <= *t).count() as f64 / observed as f64)
        })
        .collect();
    let audr = (observed > 0).then(|| {
        delays
            .iter()
            .map(|d| (1.0 - d / horizon).max(0.0))
            .sum::<f64>()
            / observed as f64
    });
    let false_rate = (exposure > 0.0).then(|| (na - matched_total) as f64 / exposure * 3600.0);
    if false_rate.is_some_and(|value| !value.is_finite()) {
        return Err("false-alert rate is not finite".into());
    }
    Ok(StreamingResult {
        n_reference: nr,
        n_observed: observed,
        n_censored: censored,
        n_matched: delays.len(),
        n_censored_matched: censored_matched,
        n_false_alerts: na - matched_total,
        exposure_seconds: exposure,
        deadline_recall: recall,
        audr,
        false_alerts_per_hour: false_rate,
        delays,
        matches,
    })
}
