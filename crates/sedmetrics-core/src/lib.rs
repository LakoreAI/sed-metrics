//! Computational core for SEDMetrics.
//!
//! This crate is independent of Python and of file formats. It provides the
//! domain types, validation and metric implementations; bindings live in
//! `sedmetrics-python`.
//!
//! All public times are seconds. Event intervals are half-open `[onset, offset)`.

pub mod matching;
pub mod metrics;
pub mod types;
pub mod validation;

pub use matching::{CollarConfig, is_eligible, maximum_matching};
pub use metrics::event::{Averaging, ClassEventF1, EventF1Config, EventF1Result, event_f1};
pub use metrics::frame::{FrameResult, frame_metrics};
pub use metrics::psds::{ClassPsds, PsdsConfig, PsdsResult, ScoreTrack, TimeUnit, psds};
pub use metrics::segment::{ClassSegmentMetrics, SegmentConfig, SegmentResult, segment_metrics};
pub use types::{Event, PredictedEvent, Recording};
pub use validation::ValidationError;
