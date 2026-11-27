"""Integration tests for segment-based metrics through the Python bindings."""

from __future__ import annotations

import json

import pytest

import sedmetrics as sm


def test_hand_computed_segment_result() -> None:
    result = sm.segment.f1(
        references=[(0, 0, 0.2, 2.1), (0, 0, 5.0, 5.5), (0, 1, 3.0, 4.0)],
        predictions=[(0, 0, 0.5, 1.5), (0, 0, 5.2, 5.4), (0, 1, 3.5, 4.2)],
        recordings={0: 10.0},
    )

    assert result.n_true_positive == 4
    assert result.n_false_positive == 1
    assert result.n_false_negative == 1
    assert result.n_substitutions == 0
    assert result.n_deletions == 1
    assert result.n_insertions == 1
    assert result.precision == pytest.approx(0.8)
    assert result.recall == pytest.approx(0.8)
    assert result.f1 == pytest.approx(0.8)
    assert result.error_rate == pytest.approx(0.4)
    assert result.n_segments == 10
    assert [stats.class_id for stats in result.classes] == [0, 1]
    assert result.config == {"segment_length": 1.0, "average": "micro"}


def test_substitution_counts_one_segment_but_two_class_errors() -> None:
    result = sm.segment.f1(
        references=[(0, 0, 7.1, 7.9)],
        predictions=[(0, 1, 7.2, 7.8)],
        recordings={0: 10.0},
    )

    assert result.n_substitutions == 1
    assert result.n_false_positive == 1
    assert result.n_false_negative == 1
    assert result.n_reference == 1
    assert result.error_rate == pytest.approx(1.0)


def test_undefined_segment_ratios_are_none() -> None:
    empty = sm.segment.f1([], [])
    assert empty.precision is None
    assert empty.f1 is None
    assert empty.error_rate is None

    no_predictions = sm.segment.f1([(0, 0, 0.0, 1.0)], [], recordings={0: 2.0})
    assert no_predictions.precision is None
    assert no_predictions.recall == 0.0
    assert no_predictions.f1 == 0.0
    assert no_predictions.error_rate == 1.0


def test_macro_averaging_support_differs_from_micro() -> None:
    references = [(0, 0, 0.0, 3.0), (0, 1, 4.0, 5.0)]
    predictions = [(0, 0, 0.0, 3.0), (0, 1, 4.0, 5.0), (0, 1, 7.0, 8.0)]

    micro = sm.segment.f1(references, predictions, average="micro")
    macro = sm.segment.f1(references, predictions, average="macro")

    assert micro.f1 == pytest.approx(8.0 / 9.0)
    assert macro.f1 == pytest.approx((1.0 + 2.0 / 3.0) / 2.0)


def test_segment_length_changes_the_granularity() -> None:
    references = [(0, 0, 0.0, 2.0)]
    predictions = [(0, 0, 2.0, 4.0)]

    coarse = sm.segment.f1(references, predictions, segment_length=1.0)
    fine = sm.segment.f1(references, predictions, segment_length=0.5)

    assert coarse.n_true_positive == 0
    assert fine.n_true_positive == 0
    assert fine.n_reference > coarse.n_reference


def test_dataset_segment_f1_accepts_names(tmp_path) -> None:
    from sedmetrics.adapters import load_urban_sed

    annotations = tmp_path / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "test" / "soundscape_test_1.txt").write_text(
        "1.0\t2.5\tsiren\n3.0\t4.0\tdog_bark\n", encoding="utf-8"
    )
    dataset = load_urban_sed(tmp_path, split="test")

    result = dataset.segment_f1([("soundscape_test_1", "siren", 1.0, 2.5)])

    assert result.n_true_positive == 2
    assert result.n_false_negative == 1


def test_segment_validation_errors() -> None:
    with pytest.raises(sm.ValidationError, match="segment_length"):
        sm.segment.f1([], [], segment_length=0.0)
    with pytest.raises(sm.ValidationError, match="past the end"):
        sm.segment.f1([(0, 0, 0.0, 2.0)], [], recordings={0: 1.0})
    with pytest.raises(ValueError, match="average"):
        sm.segment.f1([], [], average="weighted")


def test_segment_to_dict_is_json_safe() -> None:
    result = sm.segment.f1([], [])
    payload = json.dumps(result.to_dict(), allow_nan=False)
    assert '"f1": null' in payload
    assert json.loads(payload)["n_classes"] == 0
