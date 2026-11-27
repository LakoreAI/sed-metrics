"""Parity tests for segment-based metrics against sed_eval 0.2.1.

Compares TP/FP/FN, active reference/predicted segments, the S/D/I
decomposition and the rates on fixtures and sampled real data.
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

RAW_DATA = Path(
    os.environ.get(
        "SEDMETRICS_RAW_DATA", "~/workspace/.researchs/YOLIO-WOLRD/data/raw"
    )
).expanduser()


def _entries(events: list[tuple[int, int, float, float]]) -> dict[int, list[dict]]:
    by_recording: dict[int, list[dict]] = defaultdict(list)
    for recording_id, class_id, onset, offset in events:
        by_recording[recording_id].append(
            {
                "filename": str(recording_id),
                "onset": onset,
                "offset": offset,
                "event_label": class_id,
            }
        )
    return by_recording


def sed_segment_metrics(
    references: tuple[tuple[int, int, float, float], ...],
    predictions: list[tuple[int, int, float, float]],
    durations: dict[int, float],
    classes,
    segment_length: float = 1.0,
):
    metrics = sed_eval.SegmentBasedMetrics(
        event_label_list=sorted(classes), time_resolution=float(segment_length)
    )
    references_by_recording = _entries(list(references))
    predictions_by_recording = _entries(predictions)
    for recording_id, duration in durations.items():
        metrics.evaluate(
            references_by_recording[recording_id],
            predictions_by_recording[recording_id],
            evaluated_length_seconds=duration,
        )
    return metrics


def _compare(ours: float | None, theirs: float, context: str) -> None:
    if ours is None:
        assert math.isnan(theirs), f"{context}: reference defined {theirs}, ours undefined"
    elif math.isnan(theirs):
        # Documented divergence: sed_eval reports NaN when a denominator is
        # zero, we report 0 for F1 when one side is empty but the other is not.
        assert ours == 0.0, f"{context}: sed_eval NaN, ours {ours}"
    else:
        assert ours == pytest.approx(theirs, abs=1e-12), context


def assert_segment_parity(
    references,
    predictions,
    durations,
    classes,
    *,
    segment_length: float = 1.0,
    average: str = "micro",
) -> None:
    ours = sm.segment.f1(
        references,
        predictions,
        segment_length=segment_length,
        average=average,
        recordings=durations,
    )
    reference = sed_segment_metrics(
        references, predictions, durations, classes, segment_length
    )
    overall = reference.overall

    assert ours.n_true_positive == int(overall["Ntp"]), "Ntp"
    assert ours.n_false_positive == int(overall["Nfp"]), "Nfp"
    assert ours.n_false_negative == int(overall["Nfn"]), "Nfn"
    assert ours.n_reference == int(overall["Nref"]), "Nref"
    assert ours.n_predicted == int(overall["Nsys"]), "Nsys"
    assert ours.n_substitutions == int(overall["S"]), "S"
    assert ours.n_deletions == int(overall["D"]), "D"
    assert ours.n_insertions == int(overall["I"]), "I"

    rates = reference.overall_error_rate()
    _compare(ours.error_rate, rates["error_rate"], "error_rate")
    _compare(ours.substitution_rate, rates["substitution_rate"], "substitution_rate")
    _compare(ours.deletion_rate, rates["deletion_rate"], "deletion_rate")
    _compare(ours.insertion_rate, rates["insertion_rate"], "insertion_rate")

    scores = reference.overall_f_measure()
    _compare(ours.precision, scores["precision"], "precision")
    _compare(ours.recall, scores["recall"], "recall")
    _compare(ours.f1, scores["f_measure"], "f1")

    ours_by_class = {stats.class_id: stats for stats in ours.classes}
    for class_id in classes:
        theirs = reference.class_wise[class_id]
        stats = ours_by_class.get(class_id)
        assert (0 if stats is None else stats.n_true_positive) == int(theirs["Ntp"])
        assert (0 if stats is None else stats.n_false_positive) == int(theirs["Nfp"])
        assert (0 if stats is None else stats.n_false_negative) == int(theirs["Nfn"])
        assert (0 if stats is None else stats.n_reference) == int(theirs["Nref"])
        assert (0 if stats is None else stats.n_predicted) == int(theirs["Nsys"])


def test_hand_fixture_matches_reference() -> None:
    references = ((0, 0, 0.2, 2.1), (0, 0, 5.0, 5.5), (0, 1, 3.0, 4.0))
    predictions = [(0, 0, 0.5, 1.5), (0, 0, 5.2, 5.4), (0, 1, 3.5, 4.2)]

    assert_segment_parity(references, predictions, {0: 10.0}, (0, 1))


def test_substitution_matches_reference() -> None:
    references = ((0, 0, 7.1, 7.9), (0, 1, 1.0, 2.0))
    predictions = [(0, 1, 1.0, 2.0), (0, 1, 7.2, 7.8)]

    result = sm.segment.f1(references, predictions, recordings={0: 10.0})
    assert result.n_substitutions == 1

    assert_segment_parity(references, predictions, {0: 10.0}, (0, 1))


def test_boundaries_match_reference() -> None:
    references = ((0, 0, 1.0, 2.0), (0, 0, 4.0, 5.0))
    predictions = [(0, 0, 1.0, 2.0), (0, 0, 4.999, 5.0), (0, 0, 6.0, 6.0 + 1e-9)]

    assert_segment_parity(references, predictions, {0: 10.0}, (0,))


def test_random_perturbations_match_reference() -> None:
    rng = random.Random(20261128)
    references = []
    for recording_id in range(4):
        for _ in range(15):
            onset = round(rng.uniform(0.0, 18.0), 3)
            references.append(
                (
                    recording_id,
                    rng.randrange(3),
                    onset,
                    round(onset + rng.uniform(0.05, 1.5), 3),
                )
            )
    references = tuple(references)
    durations = {recording_id: 20.0 for recording_id in range(4)}

    predictions = []
    for recording_id, class_id, onset, offset in references:
        roll = rng.random()
        if roll < 0.15:
            continue
        predicted_class = class_id if roll > 0.2 else rng.randrange(3)
        shifted_onset = max(0.0, onset + rng.uniform(-0.4, 0.4))
        shifted_offset = min(20.0, max(shifted_onset + 0.05, offset + rng.uniform(-0.4, 0.4)))
        predictions.append((recording_id, predicted_class, shifted_onset, shifted_offset))
    for _ in range(10):
        onset = round(rng.uniform(0.0, 19.0), 3)
        predictions.append(
            (rng.randrange(4), rng.randrange(3), onset, round(onset + 0.4, 3))
        )

    assert_segment_parity(references, predictions, durations, (0, 1, 2))


def test_macro_averaging_matches_reference() -> None:
    references = ((0, 0, 0.0, 3.0), (0, 1, 4.0, 5.0))
    predictions = [(0, 0, 0.0, 3.0), (0, 1, 4.0, 5.0), (0, 1, 7.0, 8.0)]

    ours = sm.segment.f1(references, predictions, average="macro")
    reference = sed_segment_metrics(references, predictions, {0: 10.0}, (0, 1))
    macro = reference.results_class_wise_average_metrics()["f_measure"]

    assert ours.f1 == pytest.approx(macro["f_measure"], abs=1e-12)


def test_missing_predictions_policy_differs_by_design() -> None:
    """sed_eval reports NaN precision/F1 for an empty system; we report None/0."""
    references = ((0, 0, 0.0, 1.0),)
    ours = sm.segment.f1(references, [], recordings={0: 2.0})
    reference = sed_segment_metrics(references, [], {0: 2.0}, (0,))
    scores = reference.overall_f_measure()

    assert ours.precision is None
    assert ours.recall == 0.0
    assert ours.f1 == 0.0
    assert math.isnan(scores["precision"])
    assert int(reference.overall["Nfn"]) == ours.n_false_negative


@pytest.mark.skipif(
    not (RAW_DATA / "URBAN-SED_v2.0.0.tar.gz").exists(),
    reason="URBAN-SED archive not found; set SEDMETRICS_RAW_DATA",
)
def test_urban_sed_parity() -> None:
    dataset = load_urban_sed(RAW_DATA / "URBAN-SED_v2.0.0.tar.gz", split="test", limit=100)
    rng = random.Random(3)
    predictions = []
    for recording_id, class_id, onset, offset in dataset.references:
        duration = dataset.durations[recording_id]
        roll = rng.random()
        if roll < 0.1:
            continue
        predicted_class = class_id if roll > 0.2 else rng.choice(sorted(dataset.class_names))
        shifted_onset = min(max(0.0, onset + rng.uniform(-0.3, 0.3)), duration - 0.05)
        shifted_offset = min(max(shifted_onset + 0.05, offset + rng.uniform(-0.3, 0.3)), duration)
        predictions.append((recording_id, predicted_class, shifted_onset, shifted_offset))

    result = sm.segment.f1(
        dataset.references, predictions, recordings=dataset.durations
    )
    assert result.n_true_positive > 0
    assert result.n_substitutions + result.n_insertions + result.n_deletions > 0

    assert_segment_parity(
        dataset.references,
        predictions,
        dict(dataset.durations),
        tuple(sorted(dataset.class_names)),
    )


@pytest.mark.skipif(
    not (RAW_DATA / "audioset_strong").is_dir(),
    reason="AudioSet strong parquet not found; set SEDMETRICS_RAW_DATA",
)
def test_audioset_strong_parity() -> None:
    pytest.importorskip("pyarrow")
    dataset = load_audioset_strong(RAW_DATA / "audioset_strong", limit=40)
    rng = random.Random(5)
    predictions = []
    for recording_id, class_id, onset, offset in dataset.references:
        duration = dataset.durations[recording_id]
        roll = rng.random()
        if roll < 0.1:
            continue
        predicted_class = class_id if roll > 0.15 else rng.choice(sorted(dataset.class_names))
        shifted_onset = min(max(0.0, onset + rng.uniform(-0.3, 0.3)), duration - 0.05)
        shifted_offset = min(max(shifted_onset + 0.05, offset + rng.uniform(-0.3, 0.3)), duration)
        predictions.append((recording_id, predicted_class, shifted_onset, shifted_offset))

    assert_segment_parity(
        dataset.references,
        predictions,
        dict(dataset.durations),
        tuple(sorted(dataset.class_names)),
    )
