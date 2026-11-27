//! Input validation.
//!
//! Validation is strict by default: malformed rows, unknown recordings,
//! non-finite values and empty intervals are reported, never silently dropped.

use std::collections::BTreeSet;
use std::fmt;

use crate::types::{Event, Recording};

/// A validation failure.
///
/// Every variant carries the offending identifiers so that callers can point at
/// the exact row that was rejected.
#[derive(Debug, Clone, PartialEq)]
pub enum ValidationError {
    /// A timestamp was NaN or infinite.
    NonFiniteTime {
        /// Recording of the offending event.
        recording_id: u32,
        /// Class of the offending event.
        class_id: u32,
        /// Which endpoint failed, `"onset"` or `"offset"`.
        field: &'static str,
        /// The rejected value.
        value: f64,
    },
    /// The onset was negative.
    NegativeOnset {
        /// Recording of the offending event.
        recording_id: u32,
        /// Class of the offending event.
        class_id: u32,
        /// The rejected onset.
        onset: f64,
    },
    /// The interval had no positive length (`offset <= onset`).
    EmptyInterval {
        /// Recording of the offending event.
        recording_id: u32,
        /// Class of the offending event.
        class_id: u32,
        /// Interval onset.
        onset: f64,
        /// Interval offset.
        offset: f64,
    },
    /// The event extended past the end of its recording.
    OutsideRecording {
        /// Recording of the offending event.
        recording_id: u32,
        /// Class of the offending event.
        class_id: u32,
        /// Event offset.
        offset: f64,
        /// Recording duration.
        duration: f64,
    },
    /// An event referenced a recording with no supplied duration.
    UnknownRecording {
        /// The unknown recording id.
        recording_id: u32,
        /// Class of the offending event.
        class_id: u32,
    },
    /// A recording duration was not finite and positive.
    InvalidRecordingDuration {
        /// The offending recording id.
        recording_id: u32,
        /// The rejected duration.
        duration: f64,
    },
    /// A recording id appeared more than once in the recording list.
    DuplicateRecording {
        /// The duplicated recording id.
        recording_id: u32,
    },
    /// A collar or ratio parameter was not usable.
    InvalidCollar {
        /// Parameter name.
        field: &'static str,
        /// The rejected value.
        value: f64,
    },
    /// A metric parameter was not usable.
    InvalidParameter {
        /// Parameter name.
        field: &'static str,
        /// The rejected value.
        value: f64,
    },
    /// A score track is malformed.
    InvalidScoreTrack {
        /// Recording of the offending track.
        recording_id: u32,
        /// What is wrong.
        reason: &'static str,
    },
    /// Two score tracks carry the same recording id.
    DuplicateScoreTrack {
        /// The duplicated recording id.
        recording_id: u32,
    },
    /// The scored classes and the referenced classes are not the same set.
    ClassVocabularyMismatch,
    /// PSDS needs at least one reference event per scored class.
    ClassWithoutReferences {
        /// The class without references.
        class_id: u32,
    },
    /// `alpha_ct` and `cttc_threshold` disagree about cross-triggers.
    InconsistentPsdsConfig,
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NonFiniteTime {
                recording_id,
                class_id,
                field,
                value,
            } => write!(
                f,
                "event {field} is not finite (recording {recording_id}, class {class_id}, value {value})"
            ),
            Self::NegativeOnset {
                recording_id,
                class_id,
                onset,
            } => write!(
                f,
                "event onset must be nonnegative (recording {recording_id}, class {class_id}, onset {onset})"
            ),
            Self::EmptyInterval {
                recording_id,
                class_id,
                onset,
                offset,
            } => write!(
                f,
                "event interval must have positive length (recording {recording_id}, class {class_id}, onset {onset}, offset {offset})"
            ),
            Self::OutsideRecording {
                recording_id,
                class_id,
                offset,
                duration,
            } => write!(
                f,
                "event ends at {offset} s, past the end of recording {recording_id} ({duration} s, class {class_id})"
            ),
            Self::UnknownRecording {
                recording_id,
                class_id,
            } => write!(
                f,
                "event references recording {recording_id}, which has no duration (class {class_id})"
            ),
            Self::InvalidRecordingDuration {
                recording_id,
                duration,
            } => write!(
                f,
                "recording {recording_id} duration must be finite and positive, got {duration}"
            ),
            Self::DuplicateRecording { recording_id } => {
                write!(f, "recording {recording_id} appears more than once")
            }
            Self::InvalidCollar { field, value } => {
                write!(f, "{field} must be finite and nonnegative, got {value}")
            }
            Self::InvalidParameter { field, value } => {
                write!(f, "{field} must be finite and positive, got {value}")
            }
            Self::InvalidScoreTrack {
                recording_id,
                reason,
            } => write!(f, "score track for recording {recording_id}: {reason}"),
            Self::DuplicateScoreTrack { recording_id } => {
                write!(f, "several score tracks for recording {recording_id}")
            }
            Self::ClassVocabularyMismatch => write!(
                f,
                "the scored classes and the reference classes must be the same set"
            ),
            Self::ClassWithoutReferences { class_id } => write!(
                f,
                "class {class_id} has no reference events, so its recall is undefined"
            ),
            Self::InconsistentPsdsConfig => write!(
                f,
                "cttc_threshold must be set if and only if alpha_ct is positive"
            ),
        }
    }
}

impl std::error::Error for ValidationError {}

/// Validate a recording list: finite positive durations, unique ids.
pub fn validate_recordings(recordings: &[Recording]) -> Result<(), ValidationError> {
    let mut seen = BTreeSet::new();
    for recording in recordings {
        if !recording.duration.is_finite() || recording.duration <= 0.0 {
            return Err(ValidationError::InvalidRecordingDuration {
                recording_id: recording.recording_id,
                duration: recording.duration,
            });
        }
        if !seen.insert(recording.recording_id) {
            return Err(ValidationError::DuplicateRecording {
                recording_id: recording.recording_id,
            });
        }
    }
    Ok(())
}

/// Validate events.
///
/// Checks per event: finite endpoints, nonnegative onset, positive interval
/// length. When `recordings` is given, also checks that every recording is
/// known and that the event does not extend past the recording end.
pub fn validate_events(
    events: &[Event],
    recordings: Option<&[Recording]>,
) -> Result<(), ValidationError> {
    let durations = recordings.map(|recordings| {
        recordings
            .iter()
            .map(|r| (r.recording_id, r.duration))
            .collect::<std::collections::BTreeMap<_, _>>()
    });

    for event in events {
        if !event.onset.is_finite() {
            return Err(ValidationError::NonFiniteTime {
                recording_id: event.recording_id,
                class_id: event.class_id,
                field: "onset",
                value: event.onset,
            });
        }
        if !event.offset.is_finite() {
            return Err(ValidationError::NonFiniteTime {
                recording_id: event.recording_id,
                class_id: event.class_id,
                field: "offset",
                value: event.offset,
            });
        }
        if event.onset < 0.0 {
            return Err(ValidationError::NegativeOnset {
                recording_id: event.recording_id,
                class_id: event.class_id,
                onset: event.onset,
            });
        }
        if event.offset <= event.onset {
            return Err(ValidationError::EmptyInterval {
                recording_id: event.recording_id,
                class_id: event.class_id,
                onset: event.onset,
                offset: event.offset,
            });
        }
        if let Some(durations) = durations.as_ref() {
            let Some(duration) = durations.get(&event.recording_id) else {
                return Err(ValidationError::UnknownRecording {
                    recording_id: event.recording_id,
                    class_id: event.class_id,
                });
            };
            if event.offset > *duration {
                return Err(ValidationError::OutsideRecording {
                    recording_id: event.recording_id,
                    class_id: event.class_id,
                    offset: event.offset,
                    duration: *duration,
                });
            }
        }
    }
    Ok(())
}
