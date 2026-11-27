//! Domain types shared by the metric implementations.

/// A sound event with a class and a temporal interval.
///
/// The interval is half-open: `[onset, offset)`. A shared endpoint alone is not
/// an overlap. Both endpoints are in seconds on the recording's time axis.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Event {
    /// Stable internal identifier of the recording.
    pub recording_id: u32,
    /// Stable internal identifier of the class.
    pub class_id: u32,
    /// Start of the interval in seconds.
    pub onset: f64,
    /// End of the interval in seconds.
    pub offset: f64,
}

impl Event {
    /// Length of the interval in seconds.
    ///
    /// Only meaningful for validated events, where `offset > onset`.
    pub fn duration(&self) -> f64 {
        self.offset - self.onset
    }
}

/// A predicted event, with an optional confidence.
///
/// Confidence semantics are not fixed here: it may be a probability or a logit
/// depending on the producing system. Metrics that require probabilities must
/// document and check that requirement themselves.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct PredictedEvent {
    /// The predicted event.
    pub event: Event,
    /// Optional confidence value.
    pub confidence: Option<f64>,
}

/// Recording metadata.
///
/// Durations are required for exposure-based metrics (for example false alerts
/// per hour) and for checking that events lie inside the recording.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Recording {
    /// Stable internal identifier of the recording.
    pub recording_id: u32,
    /// Recording duration in seconds. Must be finite and positive.
    pub duration: f64,
}
