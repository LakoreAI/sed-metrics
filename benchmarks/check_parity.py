#!/usr/bin/env python3
# /// script
# requires-python = "==3.12.*"
# dependencies = [
#   "sedmetrics==0.1.2",
#   "sed_eval==0.2.1",
#   "sed_scores_eval==0.0.4",
#   "scikit-learn==1.7.2",
#   "numpy==1.26.4",
#   "pandas==2.3.3",
#   "scipy",
#   "setuptools<81",
# ]
# ///
"""Score one set of saved score tracks with SEDMetrics and the reference toolkits.

References: sed_eval (event and segment metrics), sed_scores_eval (PSDS1 and
PSDS2) and scikit-learn (frame average precision and AUROC). Both sides run in
one process on one core, and the time to build each toolkit's input is recorded
separately from the metric itself.

    uv run benchmarks/check_parity.py --scores benchmarks/runs/scores/urban-sed-test
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_models as cm  # noqa: E402


def load_scores(directory: Path, meta: dict, name: str, window: int) -> np.ndarray:
    raw = np.load(directory / f"{name}.npy")
    if meta["score_columns"] != meta["classes"]:  # AudioSet output mapped to URBAN-SED
        column = {c: i for i, c in enumerate(meta["score_columns"])}
        raw = np.stack([
            raw[[column[s] for s in cm.URBAN_SED_MAPPING[target]]].max(axis=0)
            for target in meta["classes"]
        ])
    return cm.median(raw.astype(np.float32), window)


class Clock:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)

    def __call__(self, label, function, *args, **kwargs):
        start = time.perf_counter()
        value = function(*args, **kwargs)
        self.seconds[label] += time.perf_counter() - start
        return value


def check(directory: Path, name: str, window: int, thresholds) -> dict:
    import pandas as pd
    import sed_eval
    import sed_scores_eval.intersection_based as intersection_based
    import sedmetrics as sm
    from sklearn.metrics import average_precision_score, roc_auc_score

    meta = cm.read_json(directory / "meta.json")
    classes, durations = meta["classes"], meta["durations"]
    references = [tuple(r) for r in meta["references"]]
    recordings = dict(enumerate(durations))
    scores = load_scores(directory, meta, name, window)
    ours_clock, ref_clock = Clock(), Clock()
    comparisons: dict[str, dict] = {}

    def compare(metric: str, ours, theirs) -> None:
        entry = comparisons.setdefault(metric, {"values": 0, "max_abs_difference": 0.0})
        ours = math.nan if ours is None else float(ours)
        theirs = float(theirs)
        if math.isnan(ours) and math.isnan(theirs):
            difference = 0.0
        else:
            difference = abs(ours - theirs)
        entry["values"] += 1
        if math.isnan(difference) or difference > entry["max_abs_difference"]:
            entry["max_abs_difference"] = difference
            entry["worst"] = {"sedmetrics": ours, "reference": theirs}

    predicted = []
    for c in range(len(classes)):
        value = 0.25 if thresholds is None else thresholds[c]
        predicted += cm.decode(scores[c], value, c, durations)

    # Event and segment metrics against sed_eval.
    def to_lists(events):
        out = defaultdict(list)
        for r, c, onset, offset in events:
            out[r].append({"filename": meta["ids"][r], "event_label": classes[c],
                           "onset": onset, "offset": offset})
        return out

    def sed_event():
        metrics = sed_eval.sound_event.EventBasedMetrics(
            event_label_list=classes, t_collar=0.2, percentage_of_length=0.2,
            evaluate_onset=True, evaluate_offset=True, event_matching_type="optimal")
        a, b = to_lists(references), to_lists(predicted)
        for r in range(len(durations)):
            metrics.evaluate(reference_event_list=a[r], estimated_event_list=b[r])
        return metrics

    def sed_segment():
        metrics = sed_eval.sound_event.SegmentBasedMetrics(
            event_label_list=classes, time_resolution=1.0)
        a, b = to_lists(references), to_lists(predicted)
        for r, duration in enumerate(durations):
            metrics.evaluate(a[r], b[r], evaluated_length_seconds=duration)
        return metrics

    theirs = ref_clock("event_f1", sed_event)
    ours = ours_clock("event_f1", sm.event.f1, references, predicted, recordings=recordings)
    compare("event_correct_count", ours.n_correct, theirs.overall["Ntp"])
    compare("event_f1_micro", ours.f1, theirs.overall_f_measure()["f_measure"])
    for item in ours.classes:
        row = theirs.class_wise[classes[item.class_id]]
        compare("event_class_counts", item.n_correct, row["Ntp"])
        compare("event_class_counts", item.n_insertions, row["Nfp"])
        compare("event_class_counts", item.n_deletions, row["Nfn"])

    theirs = ref_clock("segment_f1", sed_segment)
    ours = ours_clock("segment_f1", sm.segment.f1, references, predicted, recordings=recordings)
    for field, key in (("n_true_positive", "Ntp"), ("n_false_positive", "Nfp"),
                       ("n_false_negative", "Nfn"), ("n_substitutions", "S"),
                       ("n_deletions", "D"), ("n_insertions", "I")):
        compare("segment_counts", getattr(ours, field), theirs.overall[key])
    compare("segment_f1_micro", ours.f1, theirs.overall_f_measure()["f_measure"])
    compare("segment_error_rate", ours.error_rate, theirs.overall_error_rate()["error_rate"])

    # PSDS against sed_scores_eval.
    tracks = ours_clock("psds_input", cm.score_tracks, scores, durations)

    def frames():
        out = {}
        for r, clip in enumerate(meta["ids"]):
            boundaries = cm.frame_boundaries(durations[r])
            n = len(boundaries) - 1
            data = {"onset": boundaries[:-1], "offset": boundaries[1:]}
            for c, label in enumerate(classes):
                data[label] = scores[c, r, :n].astype(np.float64)
            out[clip] = pd.DataFrame(data)
        return out

    data_frames = ref_clock("psds_input", frames)
    # sed_scores_eval rejects overlapping events of one class; both sides get
    # the merged references.
    merged = cm.merge_references(references)
    truth = {clip: [] for clip in meta["ids"]}
    for r, c, onset, offset in merged:
        truth[meta["ids"][r]].append((onset, offset, classes[c]))
    lengths = dict(zip(meta["ids"], durations))
    values = {}
    for profile, options in cm.PSDS_PROFILES.items():
        theirs = ref_clock(profile, intersection_based.psds, data_frames, truth, lengths,
                           alpha_st=1.0, unit_of_time="hour", max_efpr=100.0, num_jobs=1,
                           **options)
        ours = ours_clock(profile, sm.psds.psds, merged, tracks, recordings=recordings,
                          **options)
        compare(profile, ours.psds, theirs[0])
        for item in ours.classes:
            compare(f"{profile}_per_class", item.psds, theirs[1][classes[item.class_id]])
        unmerged = sm.psds.psds(references, tracks, recordings=recordings, **options)
        values[profile] = {"sedmetrics": ours.psds, "reference": float(theirs[0]),
                           "sedmetrics_unmerged_references": unmerged.psds}

    # Frame metrics against scikit-learn, with labels mapped independently.
    def sklearn_frames():
        out = []
        for c in range(len(classes)):
            labels, kept = [], []
            by_clip = defaultdict(list)
            for r, k, onset, offset in references:
                if k == c:
                    by_clip[r].append((onset, offset))
            for r, duration in enumerate(durations):
                edges = np.asarray(cm.frame_boundaries(duration))
                active = np.zeros(len(edges) - 1, dtype=bool)
                for onset, offset in by_clip[r]:
                    active |= (np.minimum(edges[1:], offset) - np.maximum(edges[:-1], onset)) > 0
                labels.append(active)
                kept.append(scores[c, r, : len(active)])
            y, s = np.concatenate(labels), np.concatenate(kept)
            out.append((average_precision_score(y, s), roc_auc_score(y, s)))
        return out

    theirs = ref_clock("frame_events", sklearn_frames)
    ours = ours_clock("frame_events", sm.frame.events, references, tracks,
                      recordings=recordings, threshold=0.5)
    for c, (ap, auroc) in enumerate(theirs):
        compare("frame_average_precision", ours["classes"][c]["average_precision"], ap)
        compare("frame_auroc", ours["classes"][c]["auroc"], auroc)

    return {"name": name, "clips": len(durations), "comparisons": comparisons,
            "psds": values,
            "seconds": {"sedmetrics": dict(ours_clock.seconds),
                        "reference": dict(ref_clock.seconds)}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--names", nargs="+", help="score files to check (default: all)")
    parser.add_argument("--median", type=int, default=0, help="median window in frames")
    parser.add_argument("--results", type=Path,
                        help="directory of evaluation JSON files with tuned thresholds")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    names = args.names or sorted(
        path.stem for path in args.scores.glob("*.npy") if not path.stem.endswith(".part")
    )
    runs = []
    for name in names:
        thresholds = None
        if args.results:
            stored = cm.read_json(args.results / f"{name}.json")
            thresholds = stored["validation_thresholds"]["segment_f1"]
        run = check(args.scores, name, args.median, thresholds)
        runs.append(run)
        worst = max(v["max_abs_difference"] for v in run["comparisons"].values())
        cm.log(f"{name}: largest difference {worst:.3e}")
        for metric, entry in run["comparisons"].items():
            cm.log(f"   {metric:26s} n={entry['values']:3d} "
                   f"max diff {entry['max_abs_difference']:.3e}")
        for side, seconds in run["seconds"].items():
            cm.log(f"   {side:10s} " + ", ".join(f"{k} {v:.2f}s" for k, v in seconds.items()))
        cm.write_json(args.output, {"median_window": args.median, "runs": runs})


if __name__ == "__main__":
    main()
