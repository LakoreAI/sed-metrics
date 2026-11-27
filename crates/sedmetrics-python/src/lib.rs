//! PyO3 bindings for SEDMetrics.
//!
//! The native module only converts inputs, calls the Rust core and converts
//! results back. Everything else (ergonomics, typing) lives in the Python
//! package under `python/sedmetrics`.

use std::collections::HashMap;

use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use sedmetrics_core::{
    Averaging, ClassEventF1, CollarConfig, Event, EventF1Config, EventF1Result, Recording,
    ValidationError as CoreValidationError,
};

create_exception!(
    _native,
    ValidationError,
    PyValueError,
    "Raised when SEDMetrics input is inconsistent, malformed or out of range."
);

/// Per-class event F1 statistics.
#[pyclass(name = "ClassEventF1", module = "sedmetrics._native", frozen)]
#[derive(Clone)]
pub struct ClassEventF1Py {
    /// Class identifier.
    #[pyo3(get)]
    pub class_id: u32,
    /// Number of reference events.
    #[pyo3(get)]
    pub n_reference: u64,
    /// Number of predicted events.
    #[pyo3(get)]
    pub n_predicted: u64,
    /// Number of matched reference/prediction pairs.
    #[pyo3(get)]
    pub n_correct: u64,
    /// Unmatched predictions.
    #[pyo3(get)]
    pub n_insertions: u64,
    /// Unmatched references.
    #[pyo3(get)]
    pub n_deletions: u64,
    /// `n_correct / n_predicted`, or `None` when there are no predictions.
    #[pyo3(get)]
    pub precision: Option<f64>,
    /// `n_correct / n_reference`, or `None` when there are no references.
    #[pyo3(get)]
    pub recall: Option<f64>,
    /// F1 from counts, or `None` when all counts are zero.
    #[pyo3(get)]
    pub f1: Option<f64>,
    /// Mean absolute onset error over matched pairs, in seconds.
    #[pyo3(get)]
    pub mean_onset_error: Option<f64>,
    /// Mean absolute offset error over matched pairs, in seconds.
    #[pyo3(get)]
    pub mean_offset_error: Option<f64>,
}

#[pymethods]
impl ClassEventF1Py {
    /// Return the statistics as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("class_id", self.class_id)?;
        dict.set_item("n_reference", self.n_reference)?;
        dict.set_item("n_predicted", self.n_predicted)?;
        dict.set_item("n_correct", self.n_correct)?;
        dict.set_item("n_insertions", self.n_insertions)?;
        dict.set_item("n_deletions", self.n_deletions)?;
        dict.set_item("precision", self.precision)?;
        dict.set_item("recall", self.recall)?;
        dict.set_item("f1", self.f1)?;
        dict.set_item("mean_onset_error", self.mean_onset_error)?;
        dict.set_item("mean_offset_error", self.mean_offset_error)?;
        Ok(dict.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "ClassEventF1(class_id={}, n_reference={}, n_predicted={}, n_correct={}, f1={})",
            self.class_id,
            self.n_reference,
            self.n_predicted,
            self.n_correct,
            format_optional(self.f1)
        )
    }
}

/// Aggregate collar-based event F1 result with counts and per-class statistics.
#[pyclass(name = "EventF1Result", module = "sedmetrics._native", frozen)]
pub struct EventF1ResultPy {
    /// Aggregation used for the top-level ratios: `"micro"` or `"macro"`.
    #[pyo3(get)]
    pub average: &'static str,
    /// Total reference events.
    #[pyo3(get)]
    pub n_reference: u64,
    /// Total predicted events.
    #[pyo3(get)]
    pub n_predicted: u64,
    /// Total matched pairs.
    #[pyo3(get)]
    pub n_correct: u64,
    /// Total insertions.
    #[pyo3(get)]
    pub n_insertions: u64,
    /// Total deletions.
    #[pyo3(get)]
    pub n_deletions: u64,
    /// Precision under the configured averaging, or `None` when undefined.
    #[pyo3(get)]
    pub precision: Option<f64>,
    /// Recall under the configured averaging, or `None` when undefined.
    #[pyo3(get)]
    pub recall: Option<f64>,
    /// F1 under the configured averaging, or `None` when undefined.
    #[pyo3(get)]
    pub f1: Option<f64>,
    /// Mean absolute onset error over matched pairs, in seconds.
    #[pyo3(get)]
    pub mean_onset_error: Option<f64>,
    /// Mean absolute offset error over matched pairs, in seconds.
    #[pyo3(get)]
    pub mean_offset_error: Option<f64>,
    /// Number of distinct classes present in references or predictions.
    #[pyo3(get)]
    pub n_classes: u64,
    /// Per-class statistics, sorted by class id.
    pub classes: Vec<ClassEventF1Py>,
    /// Configuration used for the computation.
    pub config: EventF1Config,
}

#[pymethods]
impl EventF1ResultPy {
    /// Per-class statistics, sorted by class id.
    #[getter]
    fn classes(&self) -> Vec<ClassEventF1Py> {
        self.classes.clone()
    }

    /// Configuration used for the computation.
    #[getter]
    fn config(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("onset_collar", self.config.collar.onset_collar)?;
        dict.set_item("offset_collar", self.config.collar.offset_collar)?;
        dict.set_item("offset_ratio", self.config.collar.offset_ratio)?;
        dict.set_item("evaluate_offset", self.config.collar.evaluate_offset)?;
        dict.set_item("average", self.config.average.as_str())?;
        Ok(dict.into())
    }

    /// Return the full result as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("average", self.average)?;
        dict.set_item("n_reference", self.n_reference)?;
        dict.set_item("n_predicted", self.n_predicted)?;
        dict.set_item("n_correct", self.n_correct)?;
        dict.set_item("n_insertions", self.n_insertions)?;
        dict.set_item("n_deletions", self.n_deletions)?;
        dict.set_item("precision", self.precision)?;
        dict.set_item("recall", self.recall)?;
        dict.set_item("f1", self.f1)?;
        dict.set_item("mean_onset_error", self.mean_onset_error)?;
        dict.set_item("mean_offset_error", self.mean_offset_error)?;
        dict.set_item("n_classes", self.n_classes)?;
        dict.set_item("config", self.config(py)?)?;

        let classes = PyList::empty(py);
        for class in &self.classes {
            classes.append(class.to_dict(py)?)?;
        }
        dict.set_item("classes", classes)?;
        Ok(dict.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "EventF1Result(average='{}', f1={}, precision={}, recall={}, n_correct={}, n_insertions={}, n_deletions={})",
            self.average,
            format_optional(self.f1),
            format_optional(self.precision),
            format_optional(self.recall),
            self.n_correct,
            self.n_insertions,
            self.n_deletions
        )
    }
}

fn to_py_err(error: CoreValidationError) -> PyErr {
    ValidationError::new_err(error.to_string())
}

fn format_optional(value: Option<f64>) -> String {
    match value {
        Some(value) => format!("{value}"),
        None => "None".to_string(),
    }
}

fn field<'py>(item: &Bound<'py, PyAny>, name: &str) -> PyResult<Bound<'py, PyAny>> {
    if let Ok(value) = item.get_item(name) {
        return Ok(value);
    }
    item.getattr(name).map_err(|_| {
        PyValueError::new_err(format!(
            "event is missing field '{name}'; expected a 4-item sequence \
             (recording_id, class_id, onset, offset), a mapping or an object with those fields"
        ))
    })
}

fn extract_event(item: &Bound<'_, PyAny>) -> PyResult<Event> {
    if let Ok((recording_id, class_id, onset, offset)) = item.extract::<(u32, u32, f64, f64)>() {
        return Ok(Event {
            recording_id,
            class_id,
            onset,
            offset,
        });
    }
    Ok(Event {
        recording_id: field(item, "recording_id")?.extract()?,
        class_id: field(item, "class_id")?.extract()?,
        onset: field(item, "onset")?.extract()?,
        offset: field(item, "offset")?.extract()?,
    })
}

fn extract_events(source: &Bound<'_, PyAny>, name: &str) -> PyResult<Vec<Event>> {
    let iterator = source
        .try_iter()
        .map_err(|_| PyValueError::new_err(format!("{name} must be an iterable of events")))?;
    let mut events = Vec::new();
    for item in iterator {
        events.push(extract_event(&item?)?);
    }
    Ok(events)
}

fn parse_average(average: Option<&str>) -> PyResult<Averaging> {
    match average.unwrap_or("micro") {
        "micro" => Ok(Averaging::Micro),
        "macro" => Ok(Averaging::Macro),
        other => Err(PyValueError::new_err(format!(
            "average must be 'micro' or 'macro', got {other:?}"
        ))),
    }
}

fn convert_class(class: ClassEventF1) -> ClassEventF1Py {
    ClassEventF1Py {
        class_id: class.class_id,
        n_reference: class.n_reference,
        n_predicted: class.n_predicted,
        n_correct: class.n_correct,
        n_insertions: class.n_insertions,
        n_deletions: class.n_deletions,
        precision: class.precision,
        recall: class.recall,
        f1: class.f1,
        mean_onset_error: class.mean_onset_error,
        mean_offset_error: class.mean_offset_error,
    }
}

fn convert_result(result: EventF1Result) -> EventF1ResultPy {
    EventF1ResultPy {
        average: result.average.as_str(),
        n_reference: result.n_reference,
        n_predicted: result.n_predicted,
        n_correct: result.n_correct,
        n_insertions: result.n_insertions,
        n_deletions: result.n_deletions,
        precision: result.precision,
        recall: result.recall,
        f1: result.f1,
        mean_onset_error: result.mean_onset_error,
        mean_offset_error: result.mean_offset_error,
        n_classes: result.n_classes,
        classes: result.classes.into_iter().map(convert_class).collect(),
        config: result.config,
    }
}

/// Evaluate collar-based event precision, recall and F1.
///
/// Parameters
/// ----------
/// references, predictions:
///     Iterables of events. Each event is a 4-item sequence
///     ``(recording_id, class_id, onset, offset)``, a mapping with those keys,
///     or an object exposing those attributes. Times are seconds and intervals
///     are half-open ``[onset, offset)``.
/// onset_collar, offset_collar:
///     Absolute tolerances in seconds.
/// offset_ratio:
///     Offset tolerance as a fraction of the reference event duration; the
///     effective offset tolerance is ``max(offset_collar, offset_ratio * duration)``.
/// evaluate_offset:
///     Set to ``False`` to run a documented onset-only protocol.
/// average:
///     ``"micro"`` (pool counts) or ``"macro"`` (mean over classes where the
///     ratio is defined).
/// recordings:
///     Optional mapping ``{recording_id: duration_seconds}``. When given, events
///     outside their recording and events of unknown recordings are rejected.
///
/// Returns
/// -------
/// EventF1Result
///     Ratios, counts, per-class statistics and the configuration used.
///     Undefined ratios are ``None``, never ``NaN``.
#[pyfunction]
#[pyo3(signature = (
    references,
    predictions,
    *,
    onset_collar=0.2,
    offset_collar=0.2,
    offset_ratio=0.2,
    evaluate_offset=true,
    average=None,
    recordings=None,
))]
#[allow(clippy::too_many_arguments)]
fn event_f1(
    references: &Bound<'_, PyAny>,
    predictions: &Bound<'_, PyAny>,
    onset_collar: f64,
    offset_collar: f64,
    offset_ratio: f64,
    evaluate_offset: bool,
    average: Option<&str>,
    recordings: Option<HashMap<u32, f64>>,
) -> PyResult<EventF1ResultPy> {
    let references = extract_events(references, "references")?;
    let predictions = extract_events(predictions, "predictions")?;
    let durations = recordings.map(|recordings| {
        let mut recordings: Vec<Recording> = recordings
            .into_iter()
            .map(|(recording_id, duration)| Recording {
                recording_id,
                duration,
            })
            .collect();
        recordings.sort_by_key(|recording| recording.recording_id);
        recordings
    });

    let config = EventF1Config {
        collar: CollarConfig {
            onset_collar,
            offset_collar,
            offset_ratio,
            evaluate_offset,
        },
        average: parse_average(average)?,
    };

    let result =
        sedmetrics_core::event_f1(&references, &predictions, &config, durations.as_deref())
            .map_err(to_py_err)?;

    Ok(convert_result(result))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<ClassEventF1Py>()?;
    module.add_class::<EventF1ResultPy>()?;
    module.add("ValidationError", module.py().get_type::<ValidationError>())?;
    module.add_function(wrap_pyfunction!(event_f1, module)?)?;
    Ok(())
}
