import pytest

from sedmetrics import Dataset, SEDMetrics


def test_simple_event_evaluation():
    result = SEDMetrics.eval([(0, 0, 0.0, 1.0)], [(0, 0, 0.0, 1.0)])
    assert result.f1 == 1.0
    assert result.n_correct == 1


def test_metric_selection_and_options():
    refs = [(0, 0, 0.0, 1.0)]
    result = SEDMetrics.eval(refs, refs, metric="segment_f1", recordings={0: 2.0})
    assert result.f1 == 1.0
    result = SEDMetrics.eval(refs, [(0, 0, 0.1, 1.0)], onset_collar=0.01)
    assert result.f1 == 0.0


def test_psds_and_invalid_arguments():
    result = SEDMetrics.eval([(0, 0, 0.0, 1.0)], metric="psds", recordings={0: 1.0}, scores={0: ([0.0, 1.0], {0: [0.9]})})
    assert result.psds == 1.0
    with pytest.raises(ValueError, match="unknown metric"):
        SEDMetrics.eval([], [], metric="unknown")
    with pytest.raises(ValueError, match="requires recordings"):
        SEDMetrics.eval([], [], metric="segment_f1")


def test_dataset_accepts_named_events():
    dataset = Dataset(
        name="example", source="fixture", references=((0, 0, 0.0, 1.0),),
        durations={0: 2.0}, class_names={0: "siren"}, recording_names={0: "clip"},
    )
    result = SEDMetrics.eval(dataset, [("clip", "siren", 0.0, 1.0)])
    assert result.f1 == 1.0


def test_multiple_metrics_and_generator_inputs():
    refs = ((0, 0, 0.0, 1.0) for _ in range(1))
    preds = ((0, 0, 0.0, 1.0) for _ in range(1))
    results = SEDMetrics.eval(
        refs, preds, recordings={0: 2.0}, metrics=["event_f1", "segment_f1", "psds"],
        scores={0: ([0.0, 1.0, 2.0], {0: [0.9, 0.1]})},
        metric_options={"event_f1": {"onset_collar": 0.1}},
    )
    assert list(results) == ["event_f1", "segment_f1", "psds"]
    assert results["event_f1"].f1 == 1.0
    assert results["segment_f1"].f1 == 1.0
    assert results["psds"].psds == 1.0


def test_metrics_list_validation():
    assert SEDMetrics.eval([], [], metrics=["event_f1"])["event_f1"].f1 is None
    with pytest.raises(ValueError, match="duplicates"):
        SEDMetrics.eval([], [], metrics=["event_f1", "event_f1"])
    with pytest.raises(ValueError, match="either metric or metrics"):
        SEDMetrics.eval([], [], metric="event_f1", metrics=["event_f1"])
    with pytest.raises(ValueError, match="unselected"):
        SEDMetrics.eval([], [], metrics=["event_f1"], metric_options={"psds": {}})
