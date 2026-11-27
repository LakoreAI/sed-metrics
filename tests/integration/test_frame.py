import pytest

from sedmetrics import frame


def test_frame_hand_example_and_weighting():
    labels = [True, False, True]
    scores = [0.9, 0.8, 0.1]
    result = frame.evaluate(labels, scores, threshold=0.5)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 0)
    assert result["f1"] == 0.5
    assert result["average_precision"] == pytest.approx(5 / 6)
    assert result["auroc"] == 0.5
    weighted = frame.evaluate(labels, scores, threshold=0.5, weighting="duration", boundaries=[0, 1, 3, 6])
    assert (weighted["tp"], weighted["fp"], weighted["fn"]) == (1, 2, 3)


def test_frame_ties_undefined_and_validation():
    result = frame.evaluate([True, False], [0.5, 0.5], threshold=0.5)
    assert result["auroc"] == result["average_precision"] == 0.5
    assert frame.evaluate([False], [0.1], threshold=0.5)["average_precision"] is None
    assert frame.evaluate([True], [0.1], threshold=0.5)["auroc"] is None
    with pytest.raises(ValueError):
        frame.evaluate([True], [0.1], threshold=0.5, weighting="duration")
    with pytest.raises(ValueError):
        frame.evaluate([1], [0.1], threshold=0.5)
    with pytest.raises(ValueError):
        frame.evaluate([True], [float("nan")], threshold=0.5)
