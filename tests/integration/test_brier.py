import pytest

from sedmetrics import SEDMetrics, frame


def test_brier_binary_and_soft_targets():
    result = SEDMetrics.eval([1.0, 0.0], scores=[0.8, 0.1], mode="probability")
    assert result["brier"] == pytest.approx(0.025)
    soft = frame.brier([0.2, 0.8], [0.2, 0.5], boundaries=[0, 1, 4], weighting="duration")
    assert soft["brier"] == pytest.approx(0.0675)
    assert soft["weight"] == 4


def test_brier_validation_and_empty():
    assert frame.brier([], [])["brier"] is None
    with pytest.raises(ValueError):
        frame.brier([0.5], [2.0])
    with pytest.raises(ValueError):
        frame.brier([float("nan")], [0.5])
    with pytest.raises(ValueError):
        frame.brier([0.5], [])
