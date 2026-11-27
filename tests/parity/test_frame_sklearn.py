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


def test_event_mapping_and_multiclass_against_independent_labels():
    refs = [(0, 0, 0.75, 1.5), (0, 0, 1.25, 1.75), (0, 1, 2.0, 3.0)]
    boundaries = [0.0, 1.0, 2.0, 3.0]
    columns = {0: [0.7, 0.4, 0.9], 1: [0.1, 0.6, 0.8]}
    result = frame.events(refs, {0: (boundaries, columns)}, recordings={0: 3.0}, threshold=0.5)
    # Independently derived by any-positive-overlap, including touching edges.
    expected = {0: [True, True, False], 1: [False, False, True]}
    for class_id in expected:
        labels = expected[class_id]
        scores = columns[class_id]
        observed = result["classes"][class_id]
        assert observed["f1"] == pytest.approx(sk.f1_score(labels, [x >= 0.5 for x in scores]))
        assert observed["auroc"] == pytest.approx(sk.roc_auc_score(labels, scores))
