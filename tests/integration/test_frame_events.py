import pytest
from sedmetrics import SEDMetrics


def test_event_to_frame_and_multiclass_aggregation():
    result = SEDMetrics.eval(
        [(0, 0, 0.9, 1.0)], mode="frame", recordings={0: 2.0}, threshold=0.5,
        scores={0: ([0.0, 1.0, 2.0], {0: [0.8, 0.2], 1: [0.1, 0.7]})},
    )
    assert result["classes"][0]["tp"] == 1
    assert result["classes"][0]["tn"] == 1
    assert result["classes"][1]["fp"] == 1
    assert result["micro"]["f1"] == pytest.approx(2 / 3)
    assert result["macro"]["f1"] == 0.5


def test_event_frame_rejects_missing_tracks_or_classes():
    with pytest.raises(ValueError, match="one track"):
        SEDMetrics.eval([], mode="frame", recordings={0: 1.0, 1: 1.0}, threshold=0.5,
                        scores={0: ([0.0, 1.0], {0: [0.5]})})
    with pytest.raises(ValueError, match="absent"):
        SEDMetrics.eval([(0, 1, 0.0, 0.5)], mode="frame", recordings={0: 1.0}, threshold=0.5,
                        scores={0: ([0.0, 1.0], {0: [0.5]})})
