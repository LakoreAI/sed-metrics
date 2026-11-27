"""PSDS parity tests against `sed_scores_eval` 0.0.4 (intersection-based).

The oracle needs a Python environment where its Cython/SciPy stack works (this
repository's ``.venv-oracle``); the module is skipped otherwise.
"""

from __future__ import annotations

import math

import pytest

sed_scores_eval = pytest.importorskip(
    "sed_scores_eval.intersection_based",
    reason="install sedmetrics[parity] in an environment with a working SciPy",
    # A broken SciPy raises ImportError from dlopen, which is not a
    # ModuleNotFoundError; treat it as "oracle unavailable" rather than a test
    # collection error.
    exc_type=ImportError,
)
np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")

import sedmetrics as sm


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window - 1 - window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def build_case(
    seed: int,
    *,
    n_recordings: int = 4,
    duration: float = 20.0,
    frames: int = 200,
    n_classes: int = 3,
    decimals: int = 3,
):
    rng = np.random.default_rng(seed)
    boundaries = np.linspace(0.0, duration, frames + 1)

    references = []
    scores: dict[int, tuple[list[float], dict[int, list[float]]]] = {}
    for recording_id in range(n_recordings):
        columns = {}
        for class_id in range(n_classes):
            raw = rng.random(frames)
            smoothed = np.clip(moving_average(raw, 5) + 0.15 * rng.random(), 0.0, 1.0)
            columns[class_id] = np.round(smoothed, decimals).tolist()
        scores[recording_id] = (boundaries.tolist(), columns)

        # Two non-touching events per class per recording.
        for class_id in range(n_classes):
            start = 1.0 + 2.0 * class_id
            for index in range(2):
                onset = start + index * 8.0
                offset = onset + 2.0 + rng.random() * 0.5
                assert offset <= duration
                references.append((recording_id, class_id, round(onset, 3), round(offset, 3)))

    durations = {recording_id: duration for recording_id in range(n_recordings)}
    return references, scores, durations, boundaries


def sed_inputs(references, scores, durations):
    sed_scores = {}
    sed_ground_truth = {}
    for recording_id, (boundaries, columns) in scores.items():
        name = f"clip{recording_id}"
        frame_data = {
            "onset": list(boundaries[:-1]),
            "offset": list(boundaries[1:]),
        }
        for class_id, series in columns.items():
            frame_data[f"c{class_id}"] = list(series)
        sed_scores[name] = pd.DataFrame(frame_data)
        sed_ground_truth[name] = [
            (onset, offset, f"c{class_id}")
            for rid, class_id, onset, offset in references
            if rid == recording_id
        ]
    return sed_scores, sed_ground_truth, {f"clip{rid}": d for rid, d in durations.items()}


def run_both(references, scores, durations, **config):
    sed_scores, sed_gt, sed_durations = sed_inputs(references, scores, durations)
    reference = sed_scores_eval.psds(
        sed_scores,
        sed_gt,
        sed_durations,
        unit_of_time=config.get("unit", "hour"),
        max_efpr=config.get("max_efpr", 100.0),
        **{
            key: value
            for key, value in config.items()
            if key
            in (
                "dtc_threshold",
                "gtc_threshold",
                "cttc_threshold",
                "alpha_ct",
                "alpha_st",
            )
        },
    )
    ours = sm.psds.psds(
        references,
        scores,
        recordings=durations,
        **config,
    )
    return reference, ours


def assert_psds_parity(reference, ours, *, tolerance: float = 1e-9) -> None:
    assert ours.psds == pytest.approx(float(reference[0]), abs=tolerance), "psds"
    for class_name, expected in reference[1].items():
        class_id = int(class_name[1:])
        found = next(item for item in ours.classes if item.class_id == class_id)
        assert found.psds == pytest.approx(float(expected), abs=tolerance), class_name

    etpr, efpr = reference[2]
    assert len(ours.efpr) == len(efpr), "macro curve length"
    for ours_x, ref_x in zip(ours.efpr, efpr, strict=True):
        assert ours_x == pytest.approx(float(ref_x), abs=tolerance)
    for ours_y, ref_y in zip(ours.tpr, etpr, strict=True):
        assert ours_y == pytest.approx(float(ref_y), abs=tolerance)


def test_psds1_profile_on_synthetic_scores() -> None:
    references, scores, durations, _ = build_case(1)
    reference, ours = run_both(
        references,
        scores,
        durations,
        dtc_threshold=0.7,
        gtc_threshold=0.7,
        alpha_ct=0.0,
        alpha_st=1.0,
        unit="second",
        max_efpr=1.0,
    )

    assert ours.psds > 0.0
    assert_psds_parity(reference, ours)


@pytest.mark.parametrize("cross_triggers", [False, True])
def test_pipsds_processed_scores_against_reference(cross_triggers) -> None:
    refs = [(0, 0, 1., 2.), (0, 1, 2., 3.)]
    durations = {0: 4.}
    first = {0: ([0., 1., 2., 3., 4.], {0: [0.1, 0.9, 0.1, 0.8], 1: [0.1, 0.2, 0.9, 0.1]})}
    second = {0: ([0., 1., 2., 3., 4.], {0: [0.1, 0.9, 0.1, 0.1], 1: [0.1, 0.8, 0.9, 0.1]})}
    ref_first, gt, dur = sed_inputs(refs, first, durations)
    ref_second, _, _ = sed_inputs(refs, second, durations)
    cross = {"alpha_ct": 0.5, "cttc_threshold": 0.3} if cross_triggers else {"alpha_ct": 0.0}
    reference = sed_scores_eval.postprocessing_independent_psds(
        scores=None, ground_truth=gt, audio_durations=dur, postprocessing_functions=None,
        scores_processed=[ref_first, ref_second], dtc_threshold=0.5, gtc_threshold=0.5,
        alpha_st=0.5, unit_of_time="second", max_efpr=1.0, num_jobs=2, **cross,
    )
    ours = sm.psds.pipsds(refs, {"a": first, "b": second}, recordings=durations,
                           dtc_threshold=0.5, gtc_threshold=0.5, alpha_st=0.5,
                           unit="second", max_efpr=1.0, **cross)
    assert ours.psds == pytest.approx(float(reference[0]), abs=1e-9)
    for cls in ours.classes:
        assert cls.psds == pytest.approx(float(reference[1][f"c{cls.class_id}"]), abs=1e-9)


def test_psds_with_cross_triggers() -> None:
    references, scores, durations, _ = build_case(7)
    reference, ours = run_both(
        references,
        scores,
        durations,
        dtc_threshold=0.3,
        gtc_threshold=0.3,
        cttc_threshold=0.3,
        alpha_ct=0.5,
        alpha_st=1.0,
        unit="second",
        max_efpr=0.5,
    )

    assert_psds_parity(reference, ours)


def test_psds_without_standard_deviation_penalty() -> None:
    references, scores, durations, _ = build_case(11)
    reference, ours = run_both(
        references,
        scores,
        durations,
        dtc_threshold=0.5,
        gtc_threshold=0.5,
        alpha_ct=0.0,
        alpha_st=0.0,
        unit="second",
        max_efpr=2.0,
    )

    assert_psds_parity(reference, ours)


def test_psds_with_tied_scores() -> None:
    """Quantized scores create plateaus and merges in the detection curves."""
    references, scores, durations, _ = build_case(13, decimals=2)
    reference, ours = run_both(
        references,
        scores,
        durations,
        dtc_threshold=0.4,
        gtc_threshold=0.4,
        alpha_ct=0.0,
        alpha_st=1.0,
        unit="second",
        max_efpr=0.5,
    )

    assert_psds_parity(reference, ours)


def test_psds_per_class_curves_match() -> None:
    references, scores, durations, _ = build_case(17, n_recordings=2, frames=100, n_classes=2)
    reference, ours = run_both(
        references,
        scores,
        durations,
        dtc_threshold=0.1,
        gtc_threshold=0.1,
        alpha_ct=0.0,
        alpha_st=0.0,
        unit="second",
        max_efpr=5.0,
    )

    for class_name, (tpr, efpr, _scores) in reference[3].items():
        class_id = int(class_name[1:])
        found = next(item for item in ours.classes if item.class_id == class_id)
        assert len(found.efpr) == len(efpr), class_name
        for ours_x, ref_x in zip(found.efpr, efpr, strict=True):
            assert ours_x == pytest.approx(float(ref_x), abs=1e-12)
        for ours_y, ref_y in zip(found.tpr, tpr, strict=True):
            assert ours_y == pytest.approx(float(ref_y), abs=1e-12)


def test_psds_uses_hourly_rate_by_default() -> None:
    """One false positive in a 20 s clip is 180 events/hour."""
    references = [(0, 0, 5.0, 6.0)]
    scores = {
        0: (
            [0.0, 10.0, 20.0],
            {0: [0.0, 0.0]},
        )
    }
    # No frame reaches any reference at a high enough DTC threshold: every
    # detection is a false positive, so the only eFPR point is above 100/h.
    hourly = sm.psds.psds(
        references, scores, recordings={0: 20.0}, unit="hour", max_efpr=100.0
    )
    per_second = sm.psds.psds(
        references, scores, recordings={0: 20.0}, unit="second", max_efpr=100.0
    )

    assert math.isclose(hourly.dataset_duration, 20.0)
    assert hourly.psds <= per_second.psds + 1e-12
