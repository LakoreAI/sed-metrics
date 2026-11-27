"""Binary frame parity on finite inputs, including ties and sample weights."""
import pytest

sk = pytest.importorskip("sklearn.metrics")
from sedmetrics import frame


@pytest.mark.parametrize("weighting", ["frame", "duration"])
def test_binary_metrics_against_sklearn(weighting):
    labels = [True, False, True, False, True]
    scores = [0.5, 0.5, 0.3, -1.0, 0.9]
    boundaries = [0., 1., 3., 3.5, 4., 7.]
    weights = [1., 2., 0.5, 0.5, 3.] if weighting == "duration" else None
    result = frame.evaluate(labels, scores, threshold=0.5, weighting=weighting, boundaries=boundaries)
    assert result["average_precision"] == pytest.approx(sk.average_precision_score(labels, scores, sample_weight=weights), abs=1e-12)
    assert result["auroc"] == pytest.approx(sk.roc_auc_score(labels, scores, sample_weight=weights), abs=1e-12)
    assert result["f1"] == pytest.approx(sk.f1_score(labels, [x >= 0.5 for x in scores], sample_weight=weights), abs=1e-12)
