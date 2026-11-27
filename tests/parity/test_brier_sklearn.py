import pytest

sk = pytest.importorskip("sklearn.metrics")
from sedmetrics import frame


def test_binary_brier_against_sklearn():
    targets = [1.0, 0.0, 1.0]
    predictions = [0.8, 0.1, 0.6]
    result = frame.brier(targets, predictions, boundaries=[0.0, 1.0, 3.0, 6.0], weighting="duration")
    expected = sk.brier_score_loss(targets, predictions, sample_weight=[1.0, 2.0, 3.0])
    assert result["brier"] == pytest.approx(expected, abs=1e-12)
