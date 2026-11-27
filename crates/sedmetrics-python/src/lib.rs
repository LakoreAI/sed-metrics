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

type ScoreTrackInput = (u32, Vec<u32>, Vec<f64>, Vec<f64>);

use sedmetrics_core::{
    Averaging, ClassEventF1, ClassSegmentMetrics, CollarConfig, Event, EventF1Config,
    EventF1Result, PsdsConfig, Recording, ScoreTrack, SegmentConfig, SegmentResult, TimeUnit,
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

/// Per-class segment statistics.
#[pyclass(name = "ClassSegmentMetrics", module = "sedmetrics._native", frozen)]
#[derive(Clone)]
pub struct ClassSegmentMetricsPy {
    /// Class identifier.
    #[pyo3(get)]
    pub class_id: u32,
    /// Segments active in both reference and prediction.
    #[pyo3(get)]
    pub n_true_positive: u64,
    /// Segments active only in the prediction.
    #[pyo3(get)]
    pub n_false_positive: u64,
    /// Segments active only in the reference.
    #[pyo3(get)]
    pub n_false_negative: u64,
    /// Active reference segments.
    #[pyo3(get)]
    pub n_reference: u64,
    /// Active predicted segments.
    #[pyo3(get)]
    pub n_predicted: u64,
    /// `TP / n_predicted`, or `None` when nothing was predicted.
    #[pyo3(get)]
    pub precision: Option<f64>,
    /// `TP / n_reference`, or `None` when there is no reference activity.
    #[pyo3(get)]
    pub recall: Option<f64>,
    /// F1 from counts, or `None` when both sides are empty.
    #[pyo3(get)]
    pub f1: Option<f64>,
}

#[pymethods]
impl ClassSegmentMetricsPy {
    /// Return the statistics as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("class_id", self.class_id)?;
        dict.set_item("n_true_positive", self.n_true_positive)?;
        dict.set_item("n_false_positive", self.n_false_positive)?;
        dict.set_item("n_false_negative", self.n_false_negative)?;
        dict.set_item("n_reference", self.n_reference)?;
        dict.set_item("n_predicted", self.n_predicted)?;
        dict.set_item("precision", self.precision)?;
        dict.set_item("recall", self.recall)?;
        dict.set_item("f1", self.f1)?;
        Ok(dict.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "ClassSegmentMetrics(class_id={}, n_true_positive={}, n_false_positive={}, n_false_negative={}, f1={})",
            self.class_id,
            self.n_true_positive,
            self.n_false_positive,
            self.n_false_negative,
            format_optional(self.f1)
        )
    }
}

/// Aggregate segment-based result with the S/D/I decomposition.
#[pyclass(name = "SegmentResult", module = "sedmetrics._native", frozen)]
pub struct SegmentResultPy {
    /// Aggregation used for the reported ratios.
    #[pyo3(get)]
    pub average: &'static str,
    /// Segments active in both reference and prediction.
    #[pyo3(get)]
    pub n_true_positive: u64,
    /// Segments active only in the prediction.
    #[pyo3(get)]
    pub n_false_positive: u64,
    /// Segments active only in the reference.
    #[pyo3(get)]
    pub n_false_negative: u64,
    /// Active reference segments.
    #[pyo3(get)]
    pub n_reference: u64,
    /// Active predicted segments.
    #[pyo3(get)]
    pub n_predicted: u64,
    /// Precision under the configured averaging.
    #[pyo3(get)]
    pub precision: Option<f64>,
    /// Recall under the configured averaging.
    #[pyo3(get)]
    pub recall: Option<f64>,
    /// F1 under the configured averaging.
    #[pyo3(get)]
    pub f1: Option<f64>,
    /// Segments where reference and prediction disagree on the class.
    #[pyo3(get)]
    pub n_substitutions: u64,
    /// Reference-active segments without predicted activity.
    #[pyo3(get)]
    pub n_deletions: u64,
    /// Predicted-active segments without reference activity.
    #[pyo3(get)]
    pub n_insertions: u64,
    /// `(S + D + I) / n_reference`.
    #[pyo3(get)]
    pub error_rate: Option<f64>,
    /// `S / n_reference`.
    #[pyo3(get)]
    pub substitution_rate: Option<f64>,
    /// `D / n_reference`.
    #[pyo3(get)]
    pub deletion_rate: Option<f64>,
    /// `I / n_reference`.
    #[pyo3(get)]
    pub insertion_rate: Option<f64>,
    /// Evaluated segments across recordings.
    #[pyo3(get)]
    pub n_segments: u64,
    /// Number of distinct classes present in references or predictions.
    #[pyo3(get)]
    pub n_classes: u64,
    /// Per-class statistics, sorted by class id.
    pub classes: Vec<ClassSegmentMetricsPy>,
    /// Configuration used.
    pub config: SegmentConfig,
}

#[pymethods]
impl SegmentResultPy {
    /// Per-class statistics, sorted by class id.
    #[getter]
    fn classes(&self) -> Vec<ClassSegmentMetricsPy> {
        self.classes.clone()
    }

    /// Configuration used for the computation.
    #[getter]
    fn config(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("segment_length", self.config.segment_length)?;
        dict.set_item("average", self.config.average.as_str())?;
        Ok(dict.into())
    }

    /// Return the full result as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("average", self.average)?;
        dict.set_item("n_true_positive", self.n_true_positive)?;
        dict.set_item("n_false_positive", self.n_false_positive)?;
        dict.set_item("n_false_negative", self.n_false_negative)?;
        dict.set_item("n_reference", self.n_reference)?;
        dict.set_item("n_predicted", self.n_predicted)?;
        dict.set_item("precision", self.precision)?;
        dict.set_item("recall", self.recall)?;
        dict.set_item("f1", self.f1)?;
        dict.set_item("n_substitutions", self.n_substitutions)?;
        dict.set_item("n_deletions", self.n_deletions)?;
        dict.set_item("n_insertions", self.n_insertions)?;
        dict.set_item("error_rate", self.error_rate)?;
        dict.set_item("substitution_rate", self.substitution_rate)?;
        dict.set_item("deletion_rate", self.deletion_rate)?;
        dict.set_item("insertion_rate", self.insertion_rate)?;
        dict.set_item("n_segments", self.n_segments)?;
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
            "SegmentResult(average='{}', f1={}, precision={}, recall={}, error_rate={}, n_true_positive={}, n_false_positive={}, n_false_negative={})",
            self.average,
            format_optional(self.f1),
            format_optional(self.precision),
            format_optional(self.recall),
            format_optional(self.error_rate),
            self.n_true_positive,
            self.n_false_positive,
            self.n_false_negative
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

fn extract_recordings(recordings: Option<HashMap<u32, f64>>) -> Option<Vec<Recording>> {
    recordings.map(|recordings| {
        let mut recordings: Vec<Recording> = recordings
            .into_iter()
            .map(|(recording_id, duration)| Recording {
                recording_id,
                duration,
            })
            .collect();
        recordings.sort_by_key(|recording| recording.recording_id);
        recordings
    })
}

fn convert_segment_class(class: ClassSegmentMetrics) -> ClassSegmentMetricsPy {
    ClassSegmentMetricsPy {
        class_id: class.class_id,
        n_true_positive: class.n_true_positive,
        n_false_positive: class.n_false_positive,
        n_false_negative: class.n_false_negative,
        n_reference: class.n_reference,
        n_predicted: class.n_predicted,
        precision: class.precision,
        recall: class.recall,
        f1: class.f1,
    }
}

fn convert_segment_result(result: SegmentResult) -> SegmentResultPy {
    SegmentResultPy {
        average: result.average.as_str(),
        n_true_positive: result.n_true_positive,
        n_false_positive: result.n_false_positive,
        n_false_negative: result.n_false_negative,
        n_reference: result.n_reference,
        n_predicted: result.n_predicted,
        precision: result.precision,
        recall: result.recall,
        f1: result.f1,
        n_substitutions: result.n_substitutions,
        n_deletions: result.n_deletions,
        n_insertions: result.n_insertions,
        error_rate: result.error_rate,
        substitution_rate: result.substitution_rate,
        deletion_rate: result.deletion_rate,
        insertion_rate: result.insertion_rate,
        n_segments: result.n_segments,
        n_classes: result.n_classes,
        classes: result
            .classes
            .into_iter()
            .map(convert_segment_class)
            .collect(),
        config: result.config,
    }
}

/// Evaluate segment-based precision, recall, F1 and the S/D/I error counts.
///
/// A segment of ``segment_length`` seconds is active for a class when any event
/// of that class overlaps it. Segment indices use ``floor(onset/length)`` and
/// ``ceil(offset/length)``, so a shared endpoint alone does not activate one.
///
/// Parameters
/// ----------
/// references, predictions:
///     Iterables of events, in the same spellings as :func:`event_f1`.
/// segment_length:
///     Segment length in seconds (default 1.0).
/// average:
///     ``"micro"`` (pool counts, default) or ``"macro"`` (mean over classes).
/// recordings:
///     Optional ``{recording_id: duration_seconds}``. When given, the evaluated
///     length is the recording duration; otherwise it is the latest event
///     offset. Events outside their recording are rejected.
///
/// Returns
/// -------
/// SegmentResult
///     Ratios, TP/FP/FN, the substitution/deletion/insertion decomposition,
///     error rate, per-class statistics and the configuration used. Undefined
///     ratios are ``None``.
#[pyfunction]
#[pyo3(signature = (
    references,
    predictions,
    *,
    segment_length=1.0,
    average=None,
    recordings=None,
))]
fn segment_f1(
    references: &Bound<'_, PyAny>,
    predictions: &Bound<'_, PyAny>,
    segment_length: f64,
    average: Option<&str>,
    recordings: Option<HashMap<u32, f64>>,
) -> PyResult<SegmentResultPy> {
    let references = extract_events(references, "references")?;
    let predictions = extract_events(predictions, "predictions")?;
    let recordings = extract_recordings(recordings);
    let config = SegmentConfig {
        segment_length,
        average: parse_average(average)?,
    };

    let result =
        sedmetrics_core::segment_metrics(&references, &predictions, &config, recordings.as_deref())
            .map_err(to_py_err)?;

    Ok(convert_segment_result(result))
}

/// Per-class PSDS with its operating curve.
#[pyclass(name = "ClassPsds", module = "sedmetrics._native", frozen)]
#[derive(Clone)]
pub struct ClassPsdsPy {
    /// Class identifier.
    #[pyo3(get)]
    pub class_id: u32,
    /// Number of reference events for the class.
    #[pyo3(get)]
    pub n_reference: u64,
    /// Total reference duration of the class, in seconds.
    #[pyo3(get)]
    pub reference_duration: f64,
    /// Area under this class's PSD-ROC divided by `max_efpr`.
    #[pyo3(get)]
    pub psds: f64,
    /// Effective false-positive rates of the class envelope.
    #[pyo3(get)]
    pub efpr: Vec<f64>,
    /// True-positive rates at `efpr`.
    #[pyo3(get)]
    pub tpr: Vec<f64>,
}

#[pymethods]
impl ClassPsdsPy {
    /// Return the class result as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("class_id", self.class_id)?;
        dict.set_item("n_reference", self.n_reference)?;
        dict.set_item("reference_duration", self.reference_duration)?;
        dict.set_item("psds", self.psds)?;
        dict.set_item("efpr", self.efpr.clone())?;
        dict.set_item("tpr", self.tpr.clone())?;
        Ok(dict.into())
    }

    fn __repr__(&self) -> String {
        format!(
            "ClassPsds(class_id={}, n_reference={}, psds={})",
            self.class_id, self.n_reference, self.psds
        )
    }
}

/// PSDS result with the macro curve and per-class curves.
#[pyclass(name = "PsdsResult", module = "sedmetrics._native", frozen)]
pub struct PsdsResultPy {
    /// Macro PSDS after the `alpha_st` penalty.
    #[pyo3(get)]
    pub psds: f64,
    /// Total audio duration of the evaluated recordings, in seconds.
    #[pyo3(get)]
    pub dataset_duration: f64,
    /// Effective false-positive rates of the macro curve.
    #[pyo3(get)]
    pub efpr: Vec<f64>,
    /// Effective true-positive rates of the macro curve.
    #[pyo3(get)]
    pub tpr: Vec<f64>,
    /// Per-class results, sorted by class id.
    pub classes: Vec<ClassPsdsPy>,
    /// Configuration used.
    pub config: PsdsConfig,
}

#[pymethods]
impl PsdsResultPy {
    /// Per-class results, sorted by class id.
    #[getter]
    fn classes(&self) -> Vec<ClassPsdsPy> {
        self.classes.clone()
    }

    /// Configuration used for the computation.
    #[getter]
    fn config(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("dtc_threshold", self.config.dtc_threshold)?;
        dict.set_item("gtc_threshold", self.config.gtc_threshold)?;
        dict.set_item("cttc_threshold", self.config.cttc_threshold)?;
        dict.set_item("alpha_ct", self.config.alpha_ct)?;
        dict.set_item("alpha_st", self.config.alpha_st)?;
        dict.set_item("max_efpr", self.config.max_efpr)?;
        dict.set_item("time_decimals", self.config.time_decimals)?;
        dict.set_item("unit", time_unit_name(self.config.unit))?;
        Ok(dict.into())
    }

    /// Return the result as a plain dict.
    fn to_dict(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new(py);
        dict.set_item("psds", self.psds)?;
        dict.set_item("dataset_duration", self.dataset_duration)?;
        dict.set_item("efpr", self.efpr.clone())?;
        dict.set_item("tpr", self.tpr.clone())?;
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
            "PsdsResult(psds={}, n_classes={})",
            self.psds,
            self.classes.len()
        )
    }
}

fn time_unit_name(unit: TimeUnit) -> &'static str {
    match unit {
        TimeUnit::Second => "second",
        TimeUnit::Minute => "minute",
        TimeUnit::Hour => "hour",
    }
}

fn parse_time_unit(unit: &str) -> PyResult<TimeUnit> {
    match unit {
        "second" => Ok(TimeUnit::Second),
        "minute" => Ok(TimeUnit::Minute),
        "hour" => Ok(TimeUnit::Hour),
        other => Err(PyValueError::new_err(format!(
            "unit must be 'second', 'minute' or 'hour', got {other:?}"
        ))),
    }
}

/// Compute PSDS with intersection-based DTC/GTC/CTTC criteria.
///
/// Parameters
/// ----------
/// tracks:
///     ``[(recording_id, [class_id, ...], boundaries, scores), ...]`` where
///     ``boundaries`` has one more entry than there are frames and ``scores``
///     is row-major ``[frames, len(class_ids)]``.
/// references:
///     Events as in :func:`event_f1`. Every scored class must have at least one
///     reference event, and the class sets must match exactly.
/// recordings:
///     ``{recording_id: duration_seconds}``; required for exposure.
/// dtc_threshold, gtc_threshold:
///     Intersection criteria (DCASE PSDS1: 0.7 / 0.7, PSDS2: 0.1 / 0.1).
/// cttc_threshold:
///     Cross-trigger criterion; required iff ``alpha_ct > 0``.
/// alpha_ct, alpha_st:
///     Cross-trigger weight (PSDS1: 0, PSDS2: 0.5) and standard-deviation
///     penalty (DCASE: 1.0).
/// max_efpr:
///     Upper limit of the effective false-positive rate (DCASE: 100).
/// time_decimals:
///     Rounding of criterion sums (reference: 6).
/// unit:
///     ``"second"``, ``"minute"`` or ``"hour"``.
#[pyfunction]
#[pyo3(signature = (
    tracks,
    references,
    recordings,
    *,
    dtc_threshold=0.7,
    gtc_threshold=0.7,
    cttc_threshold=None,
    alpha_ct=0.0,
    alpha_st=1.0,
    max_efpr=100.0,
    time_decimals=6,
    unit="hour",
))]
#[allow(clippy::too_many_arguments)]
fn psds(
    tracks: Vec<ScoreTrackInput>,
    references: &Bound<'_, PyAny>,
    recordings: HashMap<u32, f64>,
    dtc_threshold: f64,
    gtc_threshold: f64,
    cttc_threshold: Option<f64>,
    alpha_ct: f64,
    alpha_st: f64,
    max_efpr: f64,
    time_decimals: u32,
    unit: &str,
) -> PyResult<PsdsResultPy> {
    let references = extract_events(references, "references")?;
    let recordings = extract_recordings(Some(recordings)).expect("recordings supplied");
    let tracks: Vec<ScoreTrack> = tracks
        .into_iter()
        .map(|(recording_id, class_ids, boundaries, scores)| ScoreTrack {
            recording_id,
            class_ids,
            boundaries,
            scores: scores.into_iter().map(|score| score as f32).collect(),
        })
        .collect();
    let config = PsdsConfig {
        dtc_threshold,
        gtc_threshold,
        cttc_threshold,
        alpha_ct,
        alpha_st,
        max_efpr,
        time_decimals,
        unit: parse_time_unit(unit)?,
    };

    let result =
        sedmetrics_core::psds(&references, &tracks, &recordings, &config).map_err(to_py_err)?;

    Ok(PsdsResultPy {
        psds: result.psds,
        dataset_duration: result.dataset_duration,
        efpr: result.efpr,
        tpr: result.tpr,
        classes: result
            .classes
            .into_iter()
            .map(|class| ClassPsdsPy {
                class_id: class.class_id,
                n_reference: class.n_reference,
                reference_duration: class.reference_duration,
                psds: class.psds,
                efpr: class.efpr,
                tpr: class.tpr,
            })
            .collect(),
        config: result.config,
    })
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
    let durations = extract_recordings(recordings);

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
    module.add_class::<ClassSegmentMetricsPy>()?;
    module.add_class::<SegmentResultPy>()?;
    module.add_class::<ClassPsdsPy>()?;
    module.add_class::<PsdsResultPy>()?;
    module.add("ValidationError", module.py().get_type::<ValidationError>())?;
    module.add_function(wrap_pyfunction!(event_f1, module)?)?;
    module.add_function(wrap_pyfunction!(segment_f1, module)?)?;
    module.add_function(wrap_pyfunction!(psds, module)?)?;
    module.add_function(wrap_pyfunction!(frame_binary, module)?)?;
    module.add_function(wrap_pyfunction!(brier_score, module)?)?;
    module.add_function(wrap_pyfunction!(frame_labels, module)?)?;
    Ok(())
}

#[pyfunction]
fn frame_labels(
    references: &Bound<'_, PyAny>,
    recording_id: u32,
    duration: f64,
    class_id: u32,
    boundaries: Vec<f64>,
) -> PyResult<Vec<bool>> {
    let events = extract_events(references, "references")?;
    sedmetrics_core::labels_from_events(
        &events,
        Recording {
            recording_id,
            duration,
        },
        class_id,
        &boundaries,
    )
    .map_err(ValidationError::new_err)
}

#[pyfunction]
fn brier_score(
    py: Python<'_>,
    targets: Vec<f64>,
    probabilities: Vec<f64>,
    weights: Vec<f64>,
) -> PyResult<Py<PyDict>> {
    let result = sedmetrics_core::brier(&targets, &probabilities, &weights)
        .map_err(ValidationError::new_err)?;
    let out = PyDict::new(py);
    out.set_item("brier", result.brier)?;
    out.set_item("squared_error", result.squared_error)?;
    out.set_item("weight", result.weight)?;
    Ok(out.into())
}

#[pyfunction]
fn frame_binary(
    py: Python<'_>,
    labels: Vec<bool>,
    scores: Vec<f64>,
    weights: Vec<f64>,
    threshold: f64,
) -> PyResult<Py<PyDict>> {
    let result = sedmetrics_core::frame_metrics(&labels, &scores, &weights, threshold)
        .map_err(ValidationError::new_err)?;
    let out = PyDict::new(py);
    out.set_item("tp", result.tp)?;
    out.set_item("fp", result.fp)?;
    out.set_item("fn", result.fn_)?;
    out.set_item("tn", result.tn)?;
    out.set_item("precision", result.precision)?;
    out.set_item("recall", result.recall)?;
    out.set_item("f1", result.f1)?;
    out.set_item("average_precision", result.average_precision)?;
    out.set_item("auroc", result.auroc)?;
    Ok(out.into())
}
