"""Parity tests against sed_eval 0.2.1 (event-based, optimal matching).

sed_eval is a development/test oracle only, never a runtime dependency. The
pinned version and its extra requirements are declared in the ``parity`` extra.

Semantics compared: onset collar ``t_collar``, offset collar
``max(t_collar, percentage_of_length * reference_duration)``, one-to-one
maximum-cardinality matching, and the pooled Ntp/Nfp/Nfn counts.
"""

from __future__ import annotations

import math
import os
import random
from collections import defaultdict
from pathlib import Path

import pytest

sed_eval = pytest.importorskip(
    "sed_eval.sound_event", reason="install sedmetrics[parity] to run parity tests"
)

import sedmetrics as sm
from sedmetrics.adapters import load_audioset_strong, load_urban_sed
from sedmetrics.dataset import Dataset

RAW_DATA = Path(
    os.environ.get(
        "SEDMETRICS_RAW_DATA", "~/workspace/.researchs/YOLIO-WOLRD/data/raw"
    )
).expanduser()


def _entry(recording_name: str, class_id: int, onset: float, offset: float) -> dict:
    return {
        "filename": recording_name,
        "onset": onset,
        "offset": offset,
        "event_label": class_id,
    }


def sed_eval_reference(
    dataset: Dataset,
    predictions: list[tuple[int, int, float, float]],
    *,
    onset_collar: float = 0.2,
    offset_ratio: float = 0.2,
    evaluate_offset: bool = True,
):
    metrics = sed_eval.EventBasedMetrics(
        event_label_list=sorted(dataset.class_names),
        evaluate_onset=True,
        evaluate_offset=evaluate_offset,
        t_collar=onset_collar,
        percentage_of_length=offset_ratio,
        event_matching_type="optimal",
    )
    references_by_recording: dict[int, list[dict]] = defaultdict(list)
    predictions_by_recording: dict[int, list[dict]] = defaultdict(list)
    for recording_id, class_id, onset, offset in dataset.references:
        references_by_recording[recording_id].append(
            _entry(dataset.recording_names[recording_id], class_id, onset, offset)
        )
    for recording_id, class_id, onset, offset in predictions:
        predictions_by_recording[recording_id].append(
            _entry(dataset.recording_names[recording_id], class_id, onset, offset)
        )
    for recording_id in dataset.durations:
        metrics.evaluate(
            reference_event_list=references_by_recording[recording_id],
            estimated_event_list=predictions_by_recording[recording_id],
        )
    return metrics


def _compare_ratio(ours: float | None, theirs: float, context: str) -> None:
    if ours is None:
        assert math.isnan(theirs), f"{context}: reference defined {theirs}, ours undefined"
    else:
        assert not math.isnan(theirs), f"{context}: reference undefined, ours {ours}"
        assert ours == pytest.approx(theirs, abs=1e-12), context


def assert_parity(
    dataset: Dataset,
    predictions: list[tuple[int, int, float, float]],
    *,
    onset_collar: float = 0.2,
    offset_ratio: float = 0.2,
    evaluate_offset: bool = True,
) -> None:
    ours = sm.event.f1(
        dataset.references,
        predictions,
        onset_collar=onset_collar,
        offset_collar=onset_collar,
        offset_ratio=offset_ratio,
        evaluate_offset=evaluate_offset,
        recordings=dataset.durations,
    )
    reference = sed_eval_reference(
        dataset,
        predictions,
        onset_collar=onset_collar,
        offset_ratio=offset_ratio,
        evaluate_offset=evaluate_offset,
    )

    assert ours.n_correct == int(reference.overall["Ntp"]), "Ntp"
    assert ours.n_predicted == int(reference.overall["Nsys"]), "Nsys"
    # sed_eval separates same-collar cross-class pairs as substitutions and
    # subtracts them from Nfp/Nfn; our counts follow the classification
    # convention (FP = Nsys - Ntp, FN = Nref - Ntp) and report no Nsubs.
    substitutions = int(reference.overall["Nsubs"])
    assert ours.n_insertions == int(reference.overall["Nfp"]) + substitutions, "Nfp"
    assert ours.n_deletions == int(reference.overall["Nfn"]) + substitutions, "Nfn"

    scores = reference.overall_f_measure()
    _compare_ratio(ours.precision, scores["precision"], "precision")
    _compare_ratio(ours.recall, scores["recall"], "recall")
    if ours.f1 is not None and not math.isnan(scores["f_measure"]):
        # sed_eval reports NaN for F1 when the system output is empty; that case
        # is covered by test_empty_predictions_policy_differs_by_design.
        assert ours.f1 == pytest.approx(scores["f_measure"], abs=1e-12), "f1"

    ours_by_class = {stats.class_id: stats for stats in ours.classes}
    for class_id in dataset.class_names:
        theirs = reference.class_wise[class_id]
        stats = ours_by_class.get(class_id)
        correct = 0 if stats is None else stats.n_correct
        insertions = 0 if stats is None else stats.n_insertions
        deletions = 0 if stats is None else stats.n_deletions
        assert correct == int(theirs["Ntp"]), f"class {class_id} Ntp"
        assert insertions == int(theirs["Nfp"]), f"class {class_id} Nfp"
        assert deletions == int(theirs["Nfn"]), f"class {class_id} Nfn"


def make_dataset(
    references: list[tuple[int, int, float, float]],
    *,
    recordings: tuple[int, ...] = (0, 1),
    classes: tuple[int, ...] = (0, 1),
    duration: float = 20.0,
) -> Dataset:
    return Dataset(
        name="synthetic",
        source="parity fixture",
        references=tuple(references),
        durations={recording_id: duration for recording_id in recordings},
        class_names={class_id: f"class{class_id}" for class_id in classes},
        recording_names={
            recording_id: f"rec{recording_id}" for recording_id in recordings
        },
    )


def test_hand_fixture_matches_reference() -> None:
    dataset = make_dataset(
        [
            (0, 0, 0.0, 1.0),
            (0, 0, 2.0, 3.0),
            (0, 0, 4.0, 5.0),
            (1, 1, 1.0, 2.0),
        ]
    )
    predictions = [
        (0, 0, 0.0, 1.0),
        (0, 0, 2.1, 3.05),
        (0, 0, 7.0, 8.0),
        (1, 0, 1.1, 2.0),
    ]

    assert_parity(dataset, predictions)


def test_collar_boundaries_match_reference() -> None:
    dataset = make_dataset([(0, 0, 1.0, 2.0), (0, 0, 5.0, 15.0)], classes=(0,))
    predictions = [
        # Exactly at the onset and offset collars: 0.25 s is binary-exact.
        (0, 0, 1.25, 2.25),
        # 25 % of a 10 s reference is 2.5 s, which dominates the 0.25 s collar.
        (0, 0, 5.0, 12.5),
    ]

    assert_parity(dataset, predictions, onset_collar=0.25, offset_ratio=0.25)


def test_onset_only_protocol_matches_reference() -> None:
    dataset = make_dataset([(0, 0, 1.0, 2.0), (0, 0, 3.0, 4.0)], classes=(0,))
    predictions = [(0, 0, 1.05, 9.0), (0, 0, 3.4, 4.0)]

    assert_parity(dataset, predictions, evaluate_offset=False)


def test_random_perturbations_match_reference() -> None:
    rng = random.Random(20261127)
    references = []
    for recording_id in range(4):
        for _ in range(18):
            onset = round(rng.uniform(0.0, 18.0), 3)
            references.append(
                (recording_id, rng.randrange(3), onset, round(onset + rng.uniform(0.1, 1.5), 3))
            )
    dataset = make_dataset(
        references, recordings=(0, 1, 2, 3), classes=(0, 1, 2), duration=20.0
    )

    predictions = []
    for recording_id, class_id, onset, offset in references:
        roll = rng.random()
        if roll < 0.15:
            continue  # deletion
        shifted_onset = max(0.0, onset + rng.uniform(-0.3, 0.3))
        shifted_offset = min(20.0, max(shifted_onset + 0.05, offset + rng.uniform(-0.3, 0.3)))
        predicted_class = class_id if roll > 0.2 else rng.randrange(3)
        predictions.append((recording_id, predicted_class, shifted_onset, shifted_offset))
    for _ in range(12):
        onset = round(rng.uniform(0.0, 19.0), 3)
        predictions.append(
            (rng.randrange(4), rng.randrange(3), onset, round(onset + 0.4, 3))
        )

    assert_parity(dataset, predictions)


def test_empty_predictions_policy_differs_by_design() -> None:
    """Our F1 is 0 when nothing was predicted; sed_eval reports NaN.

    This is the documented undefined-value policy: a zero denominator is
    ``None`` for precision, so sed_eval cannot express our F1 of 0. The counts
    still have to agree.
    """
    dataset = make_dataset([(0, 0, 0.0, 1.0)], recordings=(0,), classes=(0,))

    ours = sm.event.f1(dataset.references, [], recordings=dataset.durations)
    reference = sed_eval_reference(dataset, [])

    assert ours.precision is None
    assert ours.recall == 0.0
    assert ours.f1 == 0.0
    assert math.isnan(reference.overall_f_measure()["f_measure"])
    assert ours.n_deletions == int(reference.overall["Nfn"])


def _perturb(
    dataset: Dataset, *, seed: int, shift: float = 0.2
) -> list[tuple[int, int, float, float]]:
    rng = random.Random(seed)
    predictions = []
    for recording_id, class_id, onset, offset in dataset.references:
        duration = dataset.durations[recording_id]
        roll = rng.random()
        if roll < 0.1:
            continue
        predicted_class = class_id if roll > 0.18 else rng.choice(sorted(dataset.class_names))
        shifted_onset = min(max(0.0, onset + rng.uniform(-shift, shift)), duration - 0.05)
        shifted_offset = min(
            max(shifted_onset + 0.05, offset + rng.uniform(-shift, shift)), duration
        )
        predictions.append((recording_id, predicted_class, shifted_onset, shifted_offset))
    for recording_id in rng.sample(
        sorted(dataset.durations), k=max(1, dataset.n_recordings // 8)
    ):
        onset = rng.uniform(0.0, dataset.durations[recording_id] - 0.3)
        predictions.append(
            (
                recording_id,
                rng.choice(sorted(dataset.class_names)),
                onset,
                onset + 0.3,
            )
        )
    return predictions


@pytest.mark.skipif(
    not (RAW_DATA / "URBAN-SED_v2.0.0.tar.gz").exists(),
    reason="URBAN-SED archive not found; set SEDMETRICS_RAW_DATA",
)
def test_urban_sed_parity() -> None:
    dataset = load_urban_sed(RAW_DATA / "URBAN-SED_v2.0.0.tar.gz", split="test", limit=120)
    predictions = _perturb(dataset, seed=7)

    result = sm.event.f1(dataset.references, predictions, recordings=dataset.durations)
    assert result.n_correct > 0
    assert result.n_insertions > 0
    assert result.n_deletions > 0

    assert_parity(dataset, predictions)


@pytest.mark.skipif(
    not (RAW_DATA / "audioset_strong").is_dir(),
    reason="AudioSet strong parquet not found; set SEDMETRICS_RAW_DATA",
)
def test_audioset_strong_parity() -> None:
    pytest.importorskip("pyarrow")
    dataset = load_audioset_strong(RAW_DATA / "audioset_strong", limit=60)
    predictions = _perturb(dataset, seed=11)

    result = sm.event.f1(dataset.references, predictions, recordings=dataset.durations)
    assert result.n_correct > 0
    assert result.n_insertions > 0
    assert result.n_deletions > 0

    assert_parity(dataset, predictions)
