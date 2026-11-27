"""Integration tests for PSDS through the Python bindings."""

from __future__ import annotations

import json

import pytest

import sedmetrics as sm


def hand_case():
    references = [(0, 0, 1.0, 2.0)]
    scores = {
        0: (
            [0.0, 1.0, 2.0, 3.0, 4.0],
            {0: [0.1, 0.9, 0.1, 0.9]},
        )
    }
    return references, scores, {0: 4.0}


def test_hand_computed_psds() -> None:
    references, scores, recordings = hand_case()
    result = sm.psds.psds(
        references,
        scores,
        recordings=recordings,
        dtc_threshold=0.5,
        gtc_threshold=0.5,
        alpha_st=0.0,
        unit="second",
        max_efpr=1.0,
    )

    assert result.dataset_duration == 4.0
    assert result.classes[0].efpr == [0.0, 0.25]
    assert result.classes[0].tpr == [0.0, 1.0]
    assert result.psds == pytest.approx(0.75)
    assert result.config["unit"] == "second"


def test_psds_defaults_are_the_dcase_profile() -> None:
    references, scores, recordings = hand_case()
    result = sm.psds.psds(references, scores, recordings=recordings)

    assert result.config == {
        "dtc_threshold": 0.7,
        "gtc_threshold": 0.7,
        "cttc_threshold": None,
        "alpha_ct": 0.0,
        "alpha_st": 1.0,
        "max_efpr": 100.0,
        "time_decimals": 6,
        "unit": "hour",
    }


def test_dataset_psds_resolves_names(tmp_path) -> None:
    from sedmetrics.adapters import load_urban_sed

    annotations = tmp_path / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "test" / "clip_a.txt").write_text("1.0\t2.0\tsiren\n", encoding="utf-8")
    dataset = load_urban_sed(tmp_path, split="test")

    result = dataset.psds(
        {
            "clip_a": (
                [0.0, 1.0, 2.0, 3.0],
                {"siren": [0.05, 0.9, 0.9]},
            )
        },
        dtc_threshold=0.5,
        gtc_threshold=0.5,
        alpha_st=0.0,
        unit="second",
        max_efpr=1.0,
    )

    assert result.psds == pytest.approx(1.0)
    assert result.classes[0].n_reference == 1


def test_psds_rejects_bad_configuration() -> None:
    references, scores, recordings = hand_case()
    with pytest.raises(sm.ValidationError, match="cttc_threshold"):
        sm.psds.psds(references, scores, recordings=recordings, alpha_ct=0.5)
    with pytest.raises(sm.ValidationError, match="cttc_threshold"):
        sm.psds.psds(
            references,
            scores,
            recordings=recordings,
            cttc_threshold=0.3,
            alpha_ct=0.0,
        )
    with pytest.raises(sm.ValidationError, match="max_efpr"):
        sm.psds.psds(references, scores, recordings=recordings, max_efpr=0.0)


def test_psds_rejects_class_vocabulary_mismatch() -> None:
    references, scores, recordings = hand_case()
    scores[0][1][1] = [0.1, 0.1, 0.1, 0.1]
    with pytest.raises(sm.ValidationError, match="same set"):
        sm.psds.psds(references, scores, recordings=recordings)


def test_psds_rejects_malformed_scores() -> None:
    references, scores, recordings = hand_case()

    non_finite = {0: (scores[0][0], {0: [0.1, float("nan"), 0.1, 0.1]})}
    with pytest.raises(sm.ValidationError, match="non-finite"):
        sm.psds.psds(references, non_finite, recordings=recordings)

    wrong_length = {0: (scores[0][0], {0: [0.1, 0.9]})}
    with pytest.raises(sm.ValidationError, match="wrong number"):
        sm.psds.psds(references, wrong_length, recordings=recordings)

    outside = {0: ([0.0, 1.0, 2.0, 3.0, 5.0], {0: [0.1, 0.9, 0.1, 0.9]})}
    with pytest.raises(sm.ValidationError, match="outside the recording"):
        sm.psds.psds(references, outside, recordings=recordings)


def test_psds_to_dict_is_json_safe() -> None:
    references, scores, recordings = hand_case()
    result = sm.psds.psds(references, scores, recordings=recordings)
    payload = json.dumps(result.to_dict(), allow_nan=False)

    assert json.loads(payload)["psds"] == result.psds
    assert "config" in json.loads(payload)


def test_psds_cross_trigger_requires_two_classes() -> None:
    """CTTC with a single class is well-defined here (mean over zero others)."""
    references, scores, recordings = hand_case()
    result = sm.psds.psds(
        references,
        scores,
        recordings=recordings,
        dtc_threshold=0.5,
        gtc_threshold=0.5,
        cttc_threshold=0.5,
        alpha_ct=0.5,
        alpha_st=0.0,
        unit="second",
        max_efpr=1.0,
    )
    assert result.psds == pytest.approx(0.75)
