import itertools
import random
import pytest

from sedmetrics import SEDMetrics
from sedmetrics.experimental.streaming import evaluate


def test_analytical_fixture_and_false_alert():
    refs = [(0, 0, 0., 0.5), (0, 0, 2., 2.5), (0, 0, 4., 4.5)]
    alerts = [(0, 1, 0, 0.1, 0.1, 0.1), (0, 2, 0, 2.4, 2.4, 2.4)]
    config = dict(recordings={0: 10.}, class_ids=[0], matching_window=1., deadlines=[0.25, 0.5], horizon=1., clock="simulated")
    result = evaluate(refs, alerts, **config)
    assert result["deadline_recall"] == pytest.approx([1/3, 2/3])
    assert result["audr"] == pytest.approx(0.5)
    extra = evaluate(refs, alerts + [(0, 3, 0, 7., 7., 7.)], **config)
    assert extra["audr"] == result["audr"]
    assert extra["false_alerts_per_hour"] == 360
    via_api = SEDMetrics.eval(refs, alerts=alerts, mode="streaming", **config)
    assert via_api["audr"] == result["audr"]


def test_maximum_cardinality_and_minimum_delay_against_bruteforce():
    refs = [(0, 0, 0., 0.25), (0, 0, 0.5, 0.75), (0, 0, 1., 1.25)]
    times = [0.5, 1.0, 1.5]
    alerts = [(0, i, 0, t, t, t) for i, t in enumerate(times)]
    result = evaluate(refs, alerts, recordings={0: 5.}, class_ids=[0], matching_window=1., deadlines=[0.5], horizon=1., clock="measured")
    feasible = []
    for assignment in itertools.product(range(-1, len(alerts)), repeat=len(refs)):
        chosen = [j for j in assignment if j >= 0]
        if len(set(chosen)) != len(chosen):
            continue
        delays = [times[j] - refs[i][2] for i, j in enumerate(assignment) if j >= 0]
        if all(0 <= d <= 1 for d in delays):
            feasible.append((len(delays), sum(delays)))
    optimum = min(feasible, key=lambda x: (-x[0], x[1]))
    assert len(result["matches"]) == optimum[0]
    assert sum(result["delays"]) == pytest.approx(optimum[1])


def test_censoring_and_invalid_alerts():
    refs = [(0, 0, 9.5, 10.)]
    alert = (0, 1, 0, 9.75, 9.75, 9.75)
    config = dict(recordings={0: 10.}, class_ids=[0], matching_window=1., deadlines=[0.5], horizon=1., clock="simulated")
    result = evaluate(refs, [alert], **config)
    assert result["n_censored"] == result["n_censored_matched"] == 1
    assert result["audr"] is None and result["n_false_alerts"] == 0
    with pytest.raises(ValueError):
        evaluate(refs, [alert, alert], **config)
    with pytest.raises(ValueError):
        evaluate(refs, [(0, 1, 0, 9.75, 9.5, 9.7)], **config)
    with pytest.raises(ValueError, match="unknown class"):
        evaluate(refs, [(0, 1, 2, 9.75, 9.75, None)], **config)


def test_censored_reference_can_consume_ambiguous_alert():
    refs = [(0, 0, 9., 9.1), (0, 0, 9.5, 9.6)]
    alerts = [(0, 1, 0, 9.75, 9.75, 9.75)]
    result = evaluate(refs, alerts, recordings={0: 10.}, class_ids=[0], matching_window=1.,
                      deadlines=[1.], horizon=1., clock="simulated")
    assert result["matches"] == [(1, 0)]
    assert result["n_censored_matched"] == 1
    assert result["n_observed"] == 1 and result["n_matched"] == 0
    assert result["n_false_alerts"] == 0


def test_random_small_graphs_against_exhaustive_oracle():
    rng = random.Random(4)
    for _ in range(60):
        onsets = sorted(rng.randrange(0, 9) / 4 for _ in range(3))
        times = sorted(rng.randrange(0, 13) / 4 for _ in range(3))
        refs = [(0, 0, t, t + 0.125) for t in onsets]
        alerts = [(0, i, 0, t, t, t) for i, t in enumerate(times)]
        result = evaluate(refs, alerts, recordings={0: 8.}, class_ids=[0], matching_window=1.,
                          deadlines=[0.5], horizon=1., clock="simulated")
        options = []
        for assignment in itertools.product(range(-1, 3), repeat=3):
            chosen = [j for j in assignment if j >= 0]
            delays = [times[j] - onsets[i] for i, j in enumerate(assignment) if j >= 0]
            if len(chosen) == len(set(chosen)) and all(0 <= d <= 1 for d in delays):
                options.append((len(delays), sum(delays)))
        optimum = min(options, key=lambda x: (-x[0], x[1]))
        assert len(result["matches"]) == optimum[0]
        assert sum(result["delays"]) == pytest.approx(optimum[1])
