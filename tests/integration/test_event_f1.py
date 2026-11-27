"""Integration tests for the Python bindings and the Python façade."""

from dataclasses import dataclass
import json

import pytest

import sedmetrics as sm


def test_version_is_exposed() -> None:
    assert isinstance(sm.__version__, str)
    assert sm.__version__


def test_hand_computed_fixture() -> None:
    result = sm.event.f1(
        references=[(0, 0, 0.0, 1.0), (0, 0, 2.0, 3.0), (0, 0, 4.0, 5.0)],
        predictions=[(0, 0, 0.0, 1.0), (0, 0, 2.0, 3.0), (0, 0, 7.0, 8.0)],
    )

    assert result.n_correct == 2
    assert result.n_insertions == 1
    assert result.n_deletions == 1
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1 == pytest.approx(2 / 3)
    assert result.mean_onset_error == 0.0
    assert result.config["onset_collar"] == 0.2


def test_undefined_ratios_are_none() -> None:
    empty = sm.event.f1([], [])
    assert empty.f1 is None
    assert empty.precision is None
    assert empty.recall is None

    predictions_only = sm.event.f1([], [(0, 0, 0.0, 1.0)])
    assert predictions_only.precision == 0.0
    assert predictions_only.recall is None
    assert predictions_only.f1 == 0.0

    references_only = sm.event.f1([(0, 0, 0.0, 1.0)], [])
    assert references_only.precision is None
    assert references_only.recall == 0.0


@dataclass
class Event:
    recording_id: int
    class_id: int
    onset: float
    offset: float


def test_event_input_spellings() -> None:
    references = [
        (0, 0, 0.0, 1.0),
        {"recording_id": 0, "class_id": 0, "onset": 2.0, "offset": 3.0},
        Event(recording_id=0, class_id=0, onset=4.0, offset=5.0),
    ]
    predictions = (
        event
        for event in [(0, 0, 0.0, 1.0), (0, 0, 2.0, 3.0), (0, 0, 4.0, 5.0)]
    )

    result = sm.event.f1(references, predictions)

    assert result.n_correct == 3
    assert result.f1 == 1.0


def test_macro_averaging_differs_from_micro() -> None:
    references = [(0, 0, 0.0, 1.0)]
    references += [(0, 0, index * 2.0, index * 2.0 + 1.0) for index in range(1, 10)]
    references += [(0, 1, 0.0, 1.0)]

    predictions = [(0, 0, 0.0, 1.0)]
    predictions += [(0, 1, index * 2.0, index * 2.0 + 1.0) for index in range(1, 10)]
    predictions += [(0, 1, 0.0, 1.0)]

    macro = sm.event.f1(references, predictions, average="macro")
    micro = sm.event.f1(references, predictions, average="micro")

    assert macro.f1 == pytest.approx(2 / 11)
    assert micro.f1 == pytest.approx(2 / 11)
    assert macro.precision == pytest.approx(0.55)
    assert [class_stats.class_id for class_stats in macro.classes] == [0, 1]


def test_onset_only_protocol() -> None:
    result = sm.event.f1(
        references=[(0, 0, 1.0, 2.0)],
        predictions=[(0, 0, 1.05, 9.0)],
        evaluate_offset=False,
    )
    assert result.n_correct == 1


def test_recording_durations_are_validated() -> None:
    recording = {0: 5.0}

    accepted = sm.event.f1([(0, 0, 4.0, 5.0)], [(0, 0, 4.0, 5.0)], recordings=recording)
    assert accepted.n_correct == 1

    with pytest.raises(sm.ValidationError, match="past the end of recording"):
        sm.event.f1([(0, 0, 4.5, 5.5)], [], recordings=recording)

    with pytest.raises(sm.ValidationError, match="no duration"):
        sm.event.f1([(3, 0, 0.0, 1.0)], [], recordings=recording)


@pytest.mark.parametrize(
    ("references", "match"),
    [
        ([(0, 0, float("nan"), 1.0)], "not finite"),
        ([(0, 0, 1.0, 1.0)], "positive length"),
        ([(0, 0, -0.5, 1.0)], "nonnegative"),
        ([(0, 0, float("inf"), 1.0)], "not finite"),
    ],
)
def test_malformed_events_raise(references: list, match: str) -> None:
    with pytest.raises(sm.ValidationError, match=match):
        sm.event.f1(references, [])


def test_validation_error_is_a_value_error() -> None:
    assert issubclass(sm.ValidationError, ValueError)
    with pytest.raises(ValueError):
        sm.event.f1([], [], onset_collar=-0.1)


def test_unknown_average_raises() -> None:
    with pytest.raises(ValueError, match="average"):
        sm.event.f1([], [], average="weighted")


def test_non_iterable_input_raises() -> None:
    with pytest.raises(ValueError, match="must be an iterable"):
        sm.event.f1(42, [])


def test_duplicate_predictions_do_not_add_matches() -> None:
    result = sm.event.f1(
        references=[(0, 0, 1.0, 2.0)],
        predictions=[(0, 0, 1.0, 2.0), (0, 0, 1.0, 2.0)],
    )
    assert result.n_correct == 1
    assert result.n_insertions == 1


def test_to_dict_is_json_safe() -> None:
    result = sm.event.f1([], [])
    payload = json.dumps(result.to_dict(), allow_nan=False)
    assert '"f1": null' in payload
    assert json.loads(payload)["n_classes"] == 0
