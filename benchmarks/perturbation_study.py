#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["sedmetrics==0.1.1", "numpy<2", "scipy"]
# ///
"""How each metric reacts to one controlled error, on real annotations.

SYNTHETIC DETECTORS: no model and no audio are involved. Score tracks are built
from the URBAN-SED test annotations, and each variant damages the annotated
events in one way before scoring. All variants share the same background noise
and per-event confidences, so differences come from the injected error alone.

    uv run benchmarks/perturbation_study.py --urban-sed DIR
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_models as cm  # noqa: E402

THRESHOLD = 0.25  # above all background scores, below all event confidences
BACKGROUND = (0.0, 0.2)
CONFIDENCE = (0.3, 1.0)
RATE = 0.2
DELAY = 0.4
GAP = 0.2

VARIANTS = {
    "none": "no injected error",
    "late": f"every event {DELAY} s late",
    "split": f"events of 1 s or more split by a {GAP} s hole",
    "miss": f"{RATE:.0%} of events missed",
    "extra": f"false alarms added, {RATE:.0%} of the event count",
    "confuse": f"{RATE:.0%} of events given another class",
}


def variant_events(name, events, durations, n_classes, rng):
    """``events`` are (clip, class, onset, offset, confidence)."""
    if name == "none":
        return list(events)
    if name == "late":
        return [(r, c, on + DELAY, min(off + DELAY, durations[r]), s)
                for r, c, on, off, s in events if on + DELAY < durations[r]]
    if name == "split":
        out = []
        for r, c, on, off, s in events:
            if off - on >= 1.0:
                middle = (on + off) / 2
                out += [(r, c, on, middle - GAP / 2, s), (r, c, middle + GAP / 2, off, s)]
            else:
                out.append((r, c, on, off, s))
        return out
    count = round(RATE * len(events))
    chosen = set(rng.choice(len(events), size=count, replace=False).tolist())
    if name == "miss":
        return [event for i, event in enumerate(events) if i not in chosen]
    if name == "confuse":
        out = []
        for i, (r, c, on, off, s) in enumerate(events):
            if i in chosen:
                c = (c + int(rng.integers(1, n_classes))) % n_classes
            out.append((r, c, on, off, s))
        return out
    extra = []
    for _ in range(count):
        source = events[int(rng.integers(len(events)))]
        length = source[3] - source[2]
        r = int(rng.integers(len(durations)))
        onset = float(rng.uniform(0.0, max(0.0, durations[r] - length)))
        extra.append((r, int(rng.integers(n_classes)), onset,
                      min(onset + length, durations[r]), float(rng.uniform(*CONFIDENCE))))
    return list(events) + extra


def main() -> None:
    import sedmetrics as sm

    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--urban-sed", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--work-dir", type=Path, default=cm.HERE / "runs")
    args = parser.parse_args()

    meta, _ = cm.prepare_urban_sed(args.urban_sed, "test", None)
    classes, durations = meta["classes"], meta["durations"]
    references = [tuple(r) for r in meta["references"]]
    recordings = dict(enumerate(durations))
    n_clips = len(durations)

    out = args.work_dir.resolve() / "scores" / "synthetic-urban-sed-test"
    cm.write_json(out / "meta.json", {
        **meta, "score_columns": classes, "score_dtype": "float32",
        "synthetic": True, "seed": args.seed, "threshold": THRESHOLD,
    })

    rng = np.random.default_rng(args.seed)
    background = rng.uniform(*BACKGROUND, size=(len(classes), n_clips, cm.N_FRAMES))
    background = background.astype(np.float32)
    confidence = rng.uniform(*CONFIDENCE, size=len(references))
    events = [(*reference, float(s)) for reference, s in zip(references, confidence)]
    centres = (np.arange(cm.N_FRAMES) + 0.5) * cm.FRAME_SECONDS

    merged = cm.merge_references(references)
    results = {"seed": args.seed, "clips": n_clips, "reference_events": len(references),
               "merged_reference_events": len(merged),
               "threshold": THRESHOLD, "variants": {}}
    for index, (name, description) in enumerate(VARIANTS.items()):
        damaged = variant_events(name, events, durations, len(classes),
                                 np.random.default_rng([args.seed, index]))
        scores = background.copy()
        for r, c, onset, offset, s in damaged:
            active = (centres >= onset) & (centres < offset)
            scores[c, r, active] = np.maximum(scores[c, r, active], np.float32(s))
        np.save(out / f"{name}.npy", scores)

        predicted = []
        for c in range(len(classes)):
            predicted += cm.decode(scores[c], THRESHOLD, c, durations)
        timings = {}

        def timed(label, function, *a, **k):
            clock = time.perf_counter()
            value = function(*a, **k)
            timings[label] = time.perf_counter() - clock
            return value

        event = timed("event_f1", sm.event.f1, references, predicted, recordings=recordings)
        onset = sm.event.f1(references, predicted, recordings=recordings, evaluate_offset=False)
        segment = timed("segment_f1", sm.segment.f1, references, predicted, recordings=recordings)
        tracks = timed("convert_tracks", cm.score_tracks, scores, durations)
        row = {
            "description": description,
            "predicted_events": len(predicted),
            "event_f1": event.f1,
            "event_f1_onset_only": onset.f1,
            "segment_f1": segment.f1,
            "segment_error_rate": segment.error_rate,
        }
        for profile, options in cm.PSDS_PROFILES.items():
            row[profile] = timed(profile, sm.psds.psds, merged, tracks,
                                 recordings=recordings, **options).psds
            # The same call on the annotations as published, overlaps included.
            row[f"{profile}_unmerged_references"] = sm.psds.psds(
                references, tracks, recordings=recordings, **options).psds
        frame = timed("frame_events", sm.frame.events, references, tracks,
                      recordings=recordings, threshold=THRESHOLD)
        row["frame_map"] = frame["macro"]["average_precision"]
        row["frame_f1_micro"] = frame["micro"]["f1"]
        row["seconds"] = timings
        results["variants"][name] = row
        cm.log(f"{name:8s} " + " ".join(
            f"{k}={row[k]:.4f}" for k in
            ("event_f1", "segment_f1", "segment_error_rate", "psds1", "psds2", "frame_map")))

    cm.write_json(args.work_dir.resolve() / "results" / "perturbation.json", results)


if __name__ == "__main__":
    main()
