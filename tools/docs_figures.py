"""Generate the data behind the interactive figures in the documentation.

Every score in ``docs/assets/figures/*.json`` comes from calling ``sedmetrics``.
The browser only draws it. Where a figure also shows which interval or segment
was credited, that state is derived here and checked against the counts or the
score the library returns, so a drawing cannot disagree with the metric.

    python tools/docs_figures.py          # rewrite the JSON files
    python tools/docs_figures.py --check  # fail if they are out of date
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import sedmetrics as sm
from sedmetrics._native import frame_labels
from sedmetrics.experimental.streaming import evaluate as streaming

OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "figures"

COLLAR = 0.2
OFFSET_RATIO = 0.2
CLASSES = {0: "siren", 1: "speech"}


def r(value: float, digits: int = 6) -> float:
    return round(value + 0.0, digits)


def steps(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + i * step, 4) for i in range(count + 1)]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(f"figure disagrees with the library: {message}")


def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n == 1 else many or one + 's'}"


def metric(key: str, label: str, digits: int = 2, lower_is_better: bool = False) -> dict:
    out = {"key": key, "label": label, "digits": digits}
    if lower_is_better:
        out["lowerIsBetter"] = True
    return out


def scenario(ident, label, control_label, values, build, metrics, *, unit="", default=0,
             value_labels=None, sweep=True, intro=""):
    control = {"label": control_label, "unit": unit, "values": values, "default": default}
    if value_labels:
        control["valueLabels"] = value_labels
    return {
        "id": ident,
        "label": label,
        "intro": intro,
        "control": control,
        "metrics": metrics,
        "sweep": sweep,
        "frames": [build(value) for value in values],
    }


# --- shared event helpers ----------------------------------------------------


def matched_pairs(refs, preds):
    """Pair events using the library's own eligibility test, one pair at a time."""
    used: set[int] = set()
    pairs = []
    for i, ref in enumerate(refs):
        for j, pred in enumerate(preds):
            if j not in used and sm.event.f1([ref], [pred]).n_correct == 1:
                used.add(j)
                pairs.append((i, j))
                break
    return pairs


def interval_row(label, events, states):
    items = []
    for (_, class_id, on, off), state in zip(events, states):
        items.append({"a": r(on), "b": r(off), "s": state, "t": CLASSES[class_id]})
    return {"label": label, "items": items}


# --- event F1 ----------------------------------------------------------------


def event_frame(refs, preds, note=None, collars=True, duration=10.0):
    result = sm.event.f1(refs, preds, recordings={0: duration})
    pairs = matched_pairs(refs, preds)
    check(len(pairs) == result.n_correct, "event matches")
    hit_refs = {i for i, _ in pairs}
    hit_preds = {j for _, j in pairs}
    bands = []
    if collars:
        for _, _, on, off in refs:
            tolerance = max(COLLAR, OFFSET_RATIO * (off - on))
            bands.append({"a": r(on - COLLAR), "b": r(on + COLLAR)})
            bands.append({"a": r(off - tolerance), "b": r(off + tolerance)})
    if note is None:
        note = (f"{plural(result.n_correct, 'match', 'matches')}, "
                f"{plural(result.n_insertions, 'false alarm')}, "
                f"{plural(result.n_deletions, 'miss', 'misses')}.")
    return {
        "timeline": {
            "domain": [0, duration],
            "bands": bands,
            "rows": [
                interval_row("Reference", refs, ["ref" if i in hit_refs else "missed" for i in range(len(refs))]),
                interval_row("Prediction", preds, ["hit" if j in hit_preds else "false" for j in range(len(preds))]),
            ],
        },
        "scores": {
            "precision": None if result.precision is None else r(result.precision),
            "recall": None if result.recall is None else r(result.recall),
            "f1": None if result.f1 is None else r(result.f1),
        },
        "counts": {"TP": result.n_correct, "FP": result.n_insertions, "FN": result.n_deletions},
        "note": note,
    }


def onset_case(d):
    return [(0, 0, 3.0, 6.0)], [(0, 0, round(3.0 + d, 4), 6.0)]


def offset_case(d):
    return [(0, 0, 2.0, 6.0)], [(0, 0, 2.0, round(6.0 + d, 4))]


def split_case(gap):
    return (
        [(0, 0, 2.0, 6.0)],
        [(0, 0, 2.0, round(4.0 - gap / 2, 4)), (0, 0, round(4.0 + gap / 2, 4), 6.0)],
    )


def merge_case(gap):
    refs = [(0, 0, 1.0, 3.0), (0, 0, round(3.0 + gap, 4), round(5.0 + gap, 4))]
    return refs, [(0, 0, 1.0, round(5.0 + gap, 4))]


def alarm_case(k):
    refs = [(0, 0, 1.0, 2.5), (0, 0, 5.0, 7.0)]
    extra = [(0, 0, a, round(a + 0.5, 4)) for a in (3.2, 8.0, 4.0, 9.0)[: int(k)]]
    return refs, refs + extra


def miss_case(k):
    refs = [(0, 0, a, round(a + 1.2, 4)) for a in (0.5, 2.8, 5.1, 7.4)]
    return refs, refs[: len(refs) - int(k)]


def class_case(wrong):
    refs = [(0, 0, 1.0, 3.5), (0, 1, 5.0, 8.0)]
    second = (0, 0 if wrong else 1, 5.0, 8.0)
    return refs, [refs[0], second]


def event_figure():
    m = [metric("precision", "Precision"), metric("recall", "Recall"), metric("f1", "F1")]

    def onset_note(d):
        refs, preds = onset_case(d)
        ok = sm.event.f1(refs, preds).n_correct == 1
        if abs(abs(d) - COLLAR) < 1e-9:
            verdict = "accepted" if ok else "rejected"
            note = (f"On the collar edge. In binary arithmetic this difference is "
                    f"{abs(preds[0][2] - 3.0):.17g} s, so it is {verdict}.")
        elif ok:
            note = f"Onset off by {abs(d):.2f} s, inside the 0.2 s collar. No penalty."
        else:
            note = (f"Onset off by {abs(d):.2f} s, outside the 0.2 s collar. "
                    "The pair counts twice: one miss and one false alarm.")
        return event_frame(refs, preds, note)

    def offset_note(d):
        refs, preds = offset_case(d)
        ok = sm.event.f1(refs, preds).n_correct == 1
        note = (f"Offset off by {abs(d):.1f} s. The 4 s event allows max(0.2, 0.2 x 4) = 0.8 s, "
                + ("so it still matches." if ok else "so the match is lost."))
        return event_frame(refs, preds, note)

    def length_case(length):
        refs = [(0, 0, 1.0, round(1.0 + length, 4))]
        preds = [(0, 0, 1.0, round(1.0 + length + 0.5, 4))]
        tolerance = max(COLLAR, OFFSET_RATIO * length)
        ok = sm.event.f1(refs, preds).n_correct == 1
        note = (f"The same 0.5 s late offset against a {length:.1f} s event. Tolerance is "
                f"{tolerance:.2f} s, so it " + ("matches." if ok else "is rejected."))
        return event_frame(refs, preds, note)

    return {
        "id": "event_f1",
        "scenarios": [
            scenario("onset", "Late or early onset", "Onset shift", steps(-0.6, 0.6, 0.05), onset_note, m,
                     unit="s", default=20),
            scenario("offset", "Late or early offset", "Offset shift", steps(-1.6, 1.6, 0.2), offset_note, m,
                     unit="s", default=8),
            scenario("length", "Event length", "Reference length", steps(0.5, 5.0, 0.5), length_case, m,
                     unit="s", default=2),
            scenario("split", "Split detection", "Gap between pieces", steps(0.0, 2.0, 0.2),
                     lambda g: event_frame(*split_case(g)), m, unit="s", default=2),
            scenario("merge", "Merged events", "Gap between events", steps(0.2, 2.0, 0.2),
                     lambda g: event_frame(*merge_case(g)), m, unit="s", default=2),
            scenario("alarm", "False alarms", "Extra detections", [0, 1, 2, 3, 4],
                     lambda k: event_frame(*alarm_case(k)), m, default=1),
            scenario("miss", "Missed events", "Events missed", [0, 1, 2, 3, 4],
                     lambda k: event_frame(*miss_case(k)), m, default=1),
            scenario("class", "Wrong class", "Second event labelled", [0, 1],
                     lambda w: event_frame(*class_case(w), collars=False), m,
                     value_labels=["speech (correct)", "siren (wrong)"], default=1, sweep=False),
        ],
    }


# --- segment metrics ---------------------------------------------------------


def active_segments(events, class_id, length, n_segments):
    active = set()
    for _, c, on, off in events:
        if c == class_id:
            start = max(math.floor(on / length), 0)
            end = min(math.ceil(off / length), n_segments)
            active.update(range(start, end))
    return active


def segment_frame(refs, preds, length=1.0, duration=10.0, note=None):
    result = sm.segment.f1(refs, preds, segment_length=length, recordings={0: duration})
    n_segments = math.ceil(duration / length)
    classes = sorted({e[1] for e in refs} | {e[1] for e in preds})
    cells = []
    totals = {"tp": 0, "fp": 0, "fn": 0}
    for class_id in classes:
        ref = active_segments(refs, class_id, length, n_segments)
        pred = active_segments(preds, class_id, length, n_segments)
        items = []
        for k in range(n_segments):
            state = "tp" if k in ref and k in pred else "fn" if k in ref else "fp" if k in pred else "tn"
            if state in totals:
                totals[state] += 1
            items.append({"a": r(k * length), "b": r(min((k + 1) * length, duration)), "s": state})
        label = "Segments" if len(classes) == 1 else CLASSES[class_id].capitalize()
        cells.append({"label": label, "items": items})
    check(
        (totals["tp"], totals["fp"], totals["fn"])
        == (result.n_true_positive, result.n_false_positive, result.n_false_negative),
        "segment cells",
    )
    if note is None:
        note = (f"S {result.n_substitutions}, D {result.n_deletions}, I {result.n_insertions} "
                f"over {plural(result.n_reference, 'active reference segment')}.")
    return {
        "timeline": {
            "domain": [0, duration],
            "grid": length,
            "rows": [
                interval_row("Reference", refs, ["ref"] * len(refs)),
                interval_row("Prediction", preds, ["plain"] * len(preds)),
            ],
            "cells": cells,
        },
        "scores": {
            "precision": None if result.precision is None else r(result.precision),
            "recall": None if result.recall is None else r(result.recall),
            "f1": None if result.f1 is None else r(result.f1),
            "error_rate": None if result.error_rate is None else r(result.error_rate),
        },
        "counts": {"TP": result.n_true_positive, "FP": result.n_false_positive,
                   "FN": result.n_false_negative},
        "note": note,
    }


def segment_figure():
    m = [metric("precision", "Precision"), metric("recall", "Recall"), metric("f1", "F1"),
         metric("error_rate", "Error rate", lower_is_better=True)]

    def length_case(length):
        return segment_frame([(0, 0, 3.0, 6.0)], [(0, 0, 3.6, 6.4)], length=length)

    return {
        "id": "segment_f1",
        "scenarios": [
            scenario("onset", "Late or early onset", "Onset shift", steps(-1.5, 1.5, 0.1),
                     lambda d: segment_frame(*onset_case(d)), m, unit="s", default=21),
            scenario("length", "Segment length", "Segment length", [0.1, 0.2, 0.5, 1.0, 2.0], length_case, m,
                     unit="s", default=3,
                     intro="One prediction, 0.6 s late at the start and 0.4 s long at the end."),
            scenario("split", "Split detection", "Gap between pieces", steps(0.0, 2.4, 0.2),
                     lambda g: segment_frame(*split_case(g)), m, unit="s", default=6),
            scenario("merge", "Merged events", "Gap between events", steps(0.2, 3.0, 0.2),
                     lambda g: segment_frame(*merge_case(g)), m, unit="s", default=9),
            scenario("alarm", "False alarms", "Extra detections", [0, 1, 2, 3, 4],
                     lambda k: segment_frame(*alarm_case(k)), m, default=2),
            scenario("class", "Wrong class", "Second event labelled", [0, 1],
                     lambda w: segment_frame(*class_case(w)), m,
                     value_labels=["speech (correct)", "siren (wrong)"], default=1, sweep=False,
                     intro="A wrong label in an active segment is one substitution, not a miss plus a false alarm."),
        ],
    }


# --- frame metrics -----------------------------------------------------------

FRAME_REFS = [(0, 0, 2.0, 4.5), (0, 0, 7.0, 8.0)]
FRAME_BOUNDS = steps(0.0, 10.0, 0.25)


def frame_scores(shift=0.0):
    """A deterministic score curve: two bumps, one distractor and a ripple."""
    def bump(t, centre, width, height):
        return height * math.exp(-(((t - centre) / width) ** 4))

    scores = []
    for a, b in zip(FRAME_BOUNDS, FRAME_BOUNDS[1:]):
        t = (a + b) / 2 - shift
        value = (0.08 + bump(t, 3.2, 1.35, 0.78) + bump(t, 7.5, 0.55, 0.52)
                 + bump(t, 5.8, 0.35, 0.50) + 0.07 * math.sin(7.0 * t))
        scores.append(round(min(max(value, 0.0), 1.0), 3))
    return scores


def frame_frame(threshold, shift=0.0, note=None):
    scores = frame_scores(shift)
    result = sm.frame.events(FRAME_REFS, {0: (FRAME_BOUNDS, {0: scores})},
                             recordings={0: 10.0}, threshold=threshold)["classes"][0]
    labels = frame_labels(FRAME_REFS, 0, 10.0, 0, FRAME_BOUNDS)
    cells, totals = [], {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for a, b, label, score in zip(FRAME_BOUNDS, FRAME_BOUNDS[1:], labels, scores):
        active = score >= threshold
        state = "tp" if label and active else "fn" if label else "fp" if active else "tn"
        totals[state] += 1
        cells.append({"a": a, "b": b, "s": state})
    check(all(totals[k] == result[k] for k in totals), "frame cells")
    if note is None:
        note = (f"At threshold {threshold:.2f}: {totals['tp']} frames hit, {totals['fp']} false, "
                f"{totals['fn']} missed.")
    return {
        "timeline": {
            "domain": [0, 10],
            "rows": [interval_row("Reference", FRAME_REFS, ["ref"] * 2)],
            "series": {"label": "Score", "threshold": threshold,
                       "steps": [[a, b, s] for a, b, s in zip(FRAME_BOUNDS, FRAME_BOUNDS[1:], scores)]},
            "cells": [{"label": "Frames", "items": cells}],
        },
        "scores": {key: None if result[key] is None else r(result[key])
                   for key in ("precision", "recall", "f1", "average_precision", "auroc")},
        "counts": {k.upper(): v for k, v in totals.items()},
        "note": note,
    }


def frame_figure():
    m = [metric("precision", "Precision"), metric("recall", "Recall"), metric("f1", "F1"),
         metric("average_precision", "AP", 3), metric("auroc", "AUROC", 3)]

    def shift_case(shift):
        note = (f"Scores delayed by {shift:.2f} s, threshold fixed at 0.50. "
                "AP and AUROC fall with the ranking, F1 with the decisions.")
        return frame_frame(0.5, shift, note)

    return {
        "id": "frame",
        "scenarios": [
            scenario("threshold", "Decision threshold", "Threshold", steps(0.05, 0.95, 0.05), frame_frame, m,
                     default=9, intro="Moving the threshold changes precision, recall and F1. AP and AUROC do not move."),
            scenario("shift", "Late scores", "Delay of the score curve", steps(0.0, 2.0, 0.25), shift_case, m,
                     unit="s", default=2),
        ],
    }


# --- Brier -------------------------------------------------------------------


def brier_figure():
    grid = steps(0.0, 1.0, 0.05)

    def build(target):
        curve = [[p, r(sm.frame.brier([target], [p])["brier"])] for p in grid]

        def frame(p):
            value = sm.frame.brier([target], [p])["brier"]
            extra = ""
            if 0 < target < 1:
                extra = (f" The minimum is at p = {target:g}. A Bernoulli outcome would add "
                         f"q(1 - q) = {target * (1 - target):.2f}, which this score does not.")
            return {
                "curve": {"xLabel": "Predicted probability p", "yLabel": "Penalty", "xMax": 1, "yMax": 1,
                          "lines": [{"label": f"target {target:g}", "points": curve, "style": "main"}],
                          "marker": [p, r(value)]},
                "scores": {"brier": r(value)},
                "note": f"(p - y)^2 = ({p:.2f} - {target:g})^2 = {value:.4f}.{extra}",
            }

        return frame

    m = [metric("brier", "Brier score", 4, lower_is_better=True)]
    return {
        "id": "brier",
        "scenarios": [
            scenario(ident, label, "Predicted probability", grid, build(target), m, default=14, sweep=False)
            for ident, label, target in (
                ("positive", "Event present", 1.0),
                ("negative", "Event absent", 0.0),
                ("soft", "Soft target 0.3", 0.3),
            )
        ],
    }


# --- PSDS --------------------------------------------------------------------

PSDS1 = {"dtc_threshold": 0.7, "gtc_threshold": 0.7, "cttc_threshold": None, "alpha_ct": 0.0}
PSDS2 = {"dtc_threshold": 0.1, "gtc_threshold": 0.1, "cttc_threshold": 0.3, "alpha_ct": 0.5}


def track(duration, segments, floor=0.1):
    """Piecewise-constant scores from ``(onset, offset, score)`` segments."""
    cuts = sorted({0.0, duration, *(s[0] for s in segments), *(s[1] for s in segments)})
    cuts = [c for c in cuts if 0.0 <= c <= duration]
    values = []
    for a, b in zip(cuts, cuts[1:]):
        inside = [score for on, off, score in segments if on <= a and b <= off]
        values.append(max(inside) if inside else floor)
    return cuts, values


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def detections_at(boundaries, values, threshold):
    runs, start = [], None
    for i, value in enumerate(values):
        if value >= threshold and start is None:
            start = i
        elif value < threshold and start is not None:
            runs.append((boundaries[start], boundaries[i]))
            start = None
    if start is not None:
        runs.append((boundaries[start], boundaries[-1]))
    return runs


def psds_from_formulas(refs, scores, durations, config, alpha_st=1.0, max_efpr=100.0):
    """The formulas of docs/metrics/psds.md, written out independently."""
    classes = sorted({e[1] for e in refs})
    exposure = sum(durations.values())

    def rounded(x):
        return round(x, 6)

    curves = {}
    for c in classes:
        thresholds = sorted({v for _, cols in scores.values() for v in cols[c]}, reverse=True)
        points = [(0.0, 0.0)]
        for tau in thresholds:
            tp, fp = 0, 0
            ct = {k: 0 for k in classes if k != c}
            for rec, (boundaries, cols) in scores.items():
                dets = detections_at(boundaries, cols[c], tau)
                own = [(on, off) for rid, k, on, off in refs if rid == rec and k == c]
                relevant = [d for d in dets if rounded(sum(overlap(d, g) for g in own))
                            >= rounded(config["dtc_threshold"] * (d[1] - d[0]))]
                tp += sum(rounded(sum(overlap(d, g) for d in relevant))
                          >= rounded(config["gtc_threshold"] * (g[1] - g[0])) for g in own)
                fp += len(dets) - len(relevant)
                if config["cttc_threshold"] is not None:
                    for k in ct:
                        other = [(on, off) for rid, kk, on, off in refs if rid == rec and kk == k]
                        ct[k] += sum(d not in relevant and rounded(sum(overlap(d, g) for g in other))
                                     >= rounded(config["cttc_threshold"] * (d[1] - d[0])) for d in dets)
            efpr = fp / exposure
            if config["alpha_ct"] > 0 and ct:
                rates = [ct[k] / sum(off - on for _, kk, on, off in refs if kk == k) for k in ct]
                efpr += config["alpha_ct"] * sum(rates) / len(rates)
            points.append((efpr * 3600.0, tp / sum(1 for e in refs if e[1] == c)))
        curves[c] = [(x, y) for x, y in points if x <= max_efpr]

    def step(points, x):
        return max((y for px, y in points if px <= x), default=0.0)

    grid = sorted({x for pts in curves.values() for x, _ in pts})
    area = 0.0
    for left, right in zip(grid, grid[1:] + [max_efpr]):
        values = [step(curves[c], left) for c in classes]
        mean = sum(values) / len(values)
        std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        area += max(mean - alpha_st * std, 0.0) * (right - left)
    return area / max_efpr


def run_psds(refs, scores, durations, config, alpha_st=1.0):
    result = sm.psds.psds(refs, {rec: (b, cols) for rec, (b, cols) in scores.items()},
                          recordings=durations, alpha_st=alpha_st, **config)
    expected = psds_from_formulas(refs, scores, durations, config, alpha_st)
    check(abs(result.psds - expected) < 1e-9, f"PSDS formulas {result.psds} vs {expected}")
    return result


def silent_recordings(first_id, seconds, n, classes, level=0.0):
    """``n`` equal recordings without events that together last ``seconds``."""
    each = seconds / n
    scores = {first_id + i: ([0.0, each], {c: [level] for c in classes}) for i in range(n)}
    return scores, {first_id + i: each for i in range(n)}


def psds_case(refs, detections, exposure=3600.0, clip=10.0, floor=0.0, silent=None):
    """A visible clip plus silent recordings that supply the rest of the exposure.

    The silent audio is split into clip-sized recordings. As one long recording,
    the lowest threshold would cost a single false positive for hours of
    constant activity.
    """
    classes = sorted({e[1] for e in refs})
    columns, bounds = {}, None
    cuts = sorted({0.0, clip, *(x for segs in detections.values() for s in segs for x in s[:2] if 0 <= x <= clip)})
    for c in classes:
        values = []
        for a, b in zip(cuts, cuts[1:]):
            inside = [score for on, off, score in detections.get(c, []) if on <= a and b <= off]
            values.append(max(inside) if inside else floor)
        columns[c] = values
    bounds = cuts
    scores = {0: (bounds, columns)}
    durations = {0: clip}
    if exposure > clip:
        n = silent or round((exposure - clip) / clip)
        more_scores, more_durations = silent_recordings(1, exposure - clip, n, classes, floor)
        scores.update(more_scores)
        durations.update(more_durations)
    return scores, durations


def psds_frame(refs, detections, *, exposure=3600.0, alpha_st=1.0, note=None, threshold=0.5,
               floor=0.0, silent=None):
    scores, durations = psds_case(refs, detections, exposure, floor=floor, silent=silent)
    one = run_psds(refs, scores, durations, PSDS1, alpha_st)
    two = run_psds(refs, scores, durations, PSDS2, alpha_st)
    classes = sorted({e[1] for e in refs})
    bounds, columns = scores[0]
    ref_states, det_events, det_states = [], [], []
    found = {}
    for c in classes:
        dets = detections_at(bounds, columns[c], threshold)
        own = [(on, off) for _, k, on, off in refs if k == c]
        relevant = [d for d in dets if round(sum(overlap(d, g) for g in own), 6)
                    >= round(0.7 * (d[1] - d[0]), 6)]
        found[c] = relevant
        for d in dets:
            det_events.append((0, c, d[0], d[1]))
            det_states.append("hit" if d in relevant else "false")
    for _, c, on, off in refs:
        covered = sum(overlap(d, (on, off)) for d in found[c])
        ref_states.append("ref" if round(covered, 6) >= round(0.7 * (off - on), 6) else "missed")
    curves = [
        {"title": f"{label} operating curve", "xLabel": "Effective false positives per hour",
         "yLabel": "Effective TPR", "xMax": 100, "yMax": 1,
         "lines": [{"label": label, "style": "main", "step": True,
                    "points": [[r(x, 4), r(y)] for x, y in zip(result.efpr, result.tpr)]}]}
        for label, result in (("PSDS1", one), ("PSDS2", two))
    ]
    series = [[a, b, v] for a, b, v in zip(bounds, bounds[1:], columns[classes[0]])]
    timeline = {
        "domain": [0, 10],
        "rows": [
            interval_row("Reference", refs, ref_states),
            interval_row(f"Detections at {threshold:g}", det_events, det_states),
        ],
    }
    if len(classes) == 1:
        timeline["series"] = {"label": "Score", "threshold": threshold, "steps": series}
    return {
        "timeline": timeline,
        "curves": curves,
        "scores": {"psds1": r(one.psds), "psds2": r(two.psds)},
        "note": note,
    }


def psds_figure():
    m = [metric("psds1", "PSDS1", 3), metric("psds2", "PSDS2", 3)]
    one_ref = [(0, 0, 2.0, 5.0)]

    def long_case(end):
        inside = min(end, 5.0) - 2.0
        share, covered = inside / (end - 2.0), inside / 3.0
        note = (f"The detection runs from 2 s to {end:.1f} s. {share:.0%} of it lies on the reference (DTC) and "
                f"it covers {covered:.0%} of the reference (GTC). PSDS1 needs 70% of both, PSDS2 10%.")
        return psds_frame(one_ref, {0: [(2.0, end, 0.9)]}, note=note)

    def gap_case(gap):
        covered = (3.0 - gap) / 3.0
        pieces = [(2.0, 5.0, 0.9)] if gap == 0 else [
            (2.0, round(3.5 - gap / 2, 4), 0.9), (round(3.5 + gap / 2, 4), 5.0, 0.9)]
        note = (f"A {gap:.1f} s hole leaves {covered:.0%} of the reference covered. GTC adds the pieces "
                "together, so splitting costs nothing until the covered share drops below the threshold.")
        return psds_frame(one_ref, {0: pieces}, note=note)

    def exposure_case(seconds):
        note = (f"One false alarm scored above the true detection, over {seconds:g} s of audio: "
                f"{3600 / seconds:g} false positives per hour. The area left of that rate is lost.")
        return psds_frame(one_ref, {0: [(2.0, 5.0, 0.7), (7.0, 7.6, 0.9)]}, exposure=seconds, note=note)

    two_refs = [(0, 0, 1.0, 4.0), (0, 1, 6.0, 9.0)]

    def spread_case(alpha):
        note = (f"One class is found, the other never is. The mean TPR is 0.5 and its standard deviation 0.5, "
                f"so alpha_st = {alpha:.1f} leaves {max(0.5 - 0.5 * alpha, 0):.2f}.")
        return psds_frame(two_refs, {0: [(1.0, 4.0, 0.9)]}, alpha_st=alpha, note=note)

    def cross_case(where):
        detections = {0: [(1.0, 4.0, 0.7)], 1: [(6.0, 9.0, 0.7)]}
        note = "Both classes are detected exactly."
        if where == 1:
            detections[0].append((4.5, 5.5, 0.9))
            note = ("The siren detector also fires for 1 s on silence. Each profile counts one false positive "
                    "per hour, so each loses about 1%.")
        elif where == 2:
            detections[0].append((7.0, 8.0, 0.9))
            note = ("The same false detection on the speech event. PSDS2 also charges a cross-trigger: one over "
                    "3 s of speech, weighted 0.5, is 600 per hour, far past the limit of 100.")
        return psds_frame(two_refs, detections, note=note)

    def always_case(n):
        note = (f"Scores are 0.5 everywhere. The silent audio is in {plural(int(n), 'recording')}, so an "
                f"always-on detector costs {int(n)} false positives in one hour. PSDS2 accepts the 10 s clip "
                "because the event covers 30% of it.")
        return psds_frame(one_ref, {0: []}, floor=0.5, silent=int(n), note=note)

    return {
        "id": "psds",
        "scenarios": [
            scenario("long", "Too short or too long", "Detection ends at", steps(3.0, 9.0, 0.2), long_case, m,
                     unit="s", default=15, intro="Reference from 2 s to 5 s, one hour of audio in total."),
            scenario("gap", "Hole in a detection", "Hole length", steps(0.0, 2.4, 0.2), gap_case, m,
                     unit="s", default=5, intro="Reference from 2 s to 5 s, one hour of audio in total."),
            scenario("exposure", "Cost of a false alarm", "Audio scored",
                     [40, 50, 60, 90, 120, 180, 360, 720, 1800, 3600], exposure_case, m, unit="s", default=4),
            scenario("spread", "Uneven classes", "alpha_st", steps(0.0, 1.0, 0.1), spread_case, m, default=10),
            scenario("cross", "Cross-trigger", "Where the false detection lands", [0, 1, 2], cross_case, m,
                     value_labels=["nowhere", "on silence", "on the speech event"], default=2, sweep=False,
                     intro="Two classes, one hour of audio in total."),
            scenario("always", "Always-on detector", "Recordings holding the silent audio",
                     [1, 10, 25, 50, 100, 359], always_case, m, default=2,
                     intro="One hour of audio with a single 3 s event."),
        ],
    }


# --- piPSDS ------------------------------------------------------------------

PI_REFS = [(0, 0, 4.0, 10.0), (0, 0, 18.0, 21.0), (0, 0, 30.0, 40.0), (0, 0, 48.0, 49.5)]
PI_BOUNDS = steps(0.0, 60.0, 0.5)


def pi_raw():
    values = []
    for a in PI_BOUNDS[:-1]:
        t = a + 0.25
        inside = any(on <= t < off for _, _, on, off in PI_REFS)
        noise = 0.5 * abs(math.sin(2.3 * t) * math.cos(0.9 * t))
        value = (0.55 + noise * 0.8 - (0.3 if inside and int(t * 2) % 5 == 2 else 0)) if inside else noise
        if 24.0 <= t < 24.5 or 55.0 <= t < 56.0:
            value = 0.93
        values.append(round(min(max(value, 0.0), 1.0), 3))
    return values


def median_filter(values, width):
    half = width // 2
    padded = values[:1] * half + values + values[-1:] * half
    return [sorted(padded[i:i + width])[half] for i in range(len(values))]


def pipsds_figure():
    raw = pi_raw()
    tracks = {"raw": raw, "median 1.5 s": median_filter(raw, 3), "median 4.5 s": median_filter(raw, 9)}
    quiet, quiet_durations = silent_recordings(1, 540.0, 9, (0,))
    durations = {0: 60.0, **quiet_durations}
    processed = {name: {0: (PI_BOUNDS, {0: values}), **quiet} for name, values in tracks.items()}
    singles = {name: sm.psds.psds(PI_REFS, s, recordings=durations) for name, s in processed.items()}
    names = list(tracks)
    subsets = [[names[0]], [names[1]], [names[2]], [names[0], names[1]], [names[0], names[2]],
               [names[1], names[2]], names]

    def build(index):
        chosen = subsets[int(index)]
        envelope = sm.psds.pipsds(PI_REFS, {n: processed[n] for n in chosen}, recordings=durations)
        best = max(singles[n].psds for n in chosen)
        lines = [{"label": n, "style": "faint" if i else "alt", "step": True,
                  "points": [[r(x, 4), r(y)] for x, y in zip(singles[n].classes[0].efpr, singles[n].classes[0].tpr)]
                  + [[100, r(singles[n].classes[0].tpr[-1])]]}
                 for i, n in enumerate(chosen)]
        cls = envelope.classes[0]
        lines.append({"label": "envelope", "style": "main", "step": True,
                      "points": [[r(x, 4), r(y)] for x, y in zip(cls.efpr, cls.tpr)] + [[100, r(cls.tpr[-1])]]})
        check(envelope.psds >= best - 1e-12, "envelope below a member")
        note = (f"Best single processing in this set: {best:.3f}. The envelope takes the higher curve at every "
                f"false-positive rate and scores {envelope.psds:.3f}.")
        if len(chosen) == 1:
            note = "With one processing the envelope is that PSDS curve."
        return {"curve": {"xLabel": "Effective false positives per hour", "yLabel": "TPR", "xMax": 100, "yMax": 1,
                          "lines": lines},
                "scores": {"pipsds": r(envelope.psds), "best": r(best)}, "note": note}

    labels = [" + ".join(s) for s in subsets]
    return {
        "id": "pipsds",
        "scenarios": [
            scenario("sets", "Processings in the envelope", "Set", list(range(len(subsets))), build,
                     [metric("pipsds", "piPSDS", 3), metric("best", "Best single PSDS", 3)],
                     value_labels=labels, default=6, sweep=False),
        ],
    }


# --- streaming ---------------------------------------------------------------

DEADLINES = steps(0.0, 2.0, 0.05)


def streaming_frame(refs, alerts, note):
    kwargs = dict(recordings={0: 10.0}, class_ids=[0], matching_window=2.0, horizon=2.0, clock="simulated")
    result = streaming(refs, alerts, deadlines=[0.5, 1.0], **kwargs)
    sweep = streaming(refs, alerts, deadlines=DEADLINES, **kwargs)
    matched_alerts = {j for _, j in result["matches"]}
    matched_refs = {i for i, _ in result["matches"]}
    ref_states = []
    for i, (_, _, on, _) in enumerate(refs):
        censored = on + 2.0 > 10.0
        ref_states.append("censored" if censored else "ref" if i in matched_refs else "missed")
    curve = [[t, v] for t, v in zip(DEADLINES, sweep["deadline_recall"]) if v is not None]
    return {
        "timeline": {
            "domain": [0, 10],
            "bands": [{"a": r(on), "b": r(min(on + 2.0, 10.0))} for _, _, on, _ in refs],
            "rows": [interval_row("Reference", refs, ref_states)],
            "points": {"label": "Alerts",
                       "items": [{"t": a[3], "s": "hit" if j in matched_alerts else "false"}
                                 for j, a in enumerate(alerts)]},
        },
        "curve": {"xLabel": "Deadline t after onset (s)", "yLabel": "DAR(t)", "xMax": 2, "yMax": 1,
                  "lines": [{"label": "deadline recall", "style": "main", "step": True, "points": curve}]},
        "scores": {
            "dar05": None if result["deadline_recall"][0] is None else r(result["deadline_recall"][0]),
            "dar10": None if result["deadline_recall"][1] is None else r(result["deadline_recall"][1]),
            "audr": None if result["audr"] is None else r(result["audr"]),
            "fah": r(result["false_alerts_per_hour"]),
        },
        "counts": {"observed": result["n_observed"], "censored": result["n_censored"],
                   "false alerts": result["n_false_alerts"]},
        "note": note,
    }


def alert(ident, time):
    return (0, ident, 0, round(time, 4), round(time, 4), None)


def streaming_figure():
    m = [metric("dar05", "DAR(0.5 s)"), metric("dar10", "DAR(1 s)"), metric("audr", "AUDR"),
         metric("fah", "False alerts / h", 0, lower_is_better=True)]
    refs = [(0, 0, 2.0, 3.0), (0, 0, 6.0, 7.0)]

    def delay_case(d):
        alerts = [alert(1, 2.25), alert(2, 6.0 + d)]
        if d < 0:
            note = f"The second alert arrives {abs(d):.2f} s before the onset. It is a false alert and the event is missed."
        elif d > 2.0:
            note = f"The second alert arrives {d:.2f} s after the onset, outside the 2 s window: a miss and a false alert."
        else:
            note = (f"Delay {d:.2f} s. It adds max(0, 1 - {d:.2f} / 2) = {max(0, 1 - d / 2):.3f} "
                    "to the AUDR numerator.")
        return streaming_frame(refs, alerts, note)

    def duplicate_case(k):
        alerts = [alert(1, 2.25)] + [alert(2 + i, t) for i, t in enumerate((2.75, 3.25, 3.75)[: int(k)])]
        alerts.append(alert(10, 6.5))
        note = f"{plural(int(k), 'repeated alert')} for the first event. Only one alert can match; the rest are false."
        return streaming_frame(refs, alerts, note)

    def censor_case(onset):
        pair = [(0, 0, 2.0, 3.0), (0, 0, onset, round(onset + 0.4, 4))]
        censored = onset + 2.0 > 10.0
        note = ("The second window runs past the 10 s clip, so that reference is censored: no credit and no miss."
                if censored else "Both windows are fully observed. The second event has no alert, so it is a miss.")
        return streaming_frame(pair, [alert(1, 2.25)], note)

    return {
        "id": "streaming",
        "scenarios": [
            scenario("delay", "Alert delay", "Second alert, relative to onset", steps(-0.5, 2.5, 0.25),
                     delay_case, m, unit="s", default=5,
                     intro="Two events, a 2 s matching window and a 2 s horizon."),
            scenario("duplicate", "Repeated alerts", "Extra alerts", [0, 1, 2, 3], duplicate_case, m, default=2),
            scenario("censor", "Censoring", "Second onset", steps(6.5, 9.5, 0.5), censor_case, m,
                     unit="s", default=2),
        ],
    }


# --- cross-metric comparison -------------------------------------------------

MATRIX_REFS = [(0, 0, 2.0, 4.0), (0, 0, 5.0, 7.0), (0, 1, 10.0, 14.0)]


def matrix_predictions():
    s1, s2, sp = MATRIX_REFS
    return [
        ("exact", "Exact", "Every event with the right boundaries and class.", list(MATRIX_REFS)),
        ("late", "Onsets 0.15 s late", "Inside the 0.2 s collar.",
         [(0, c, round(on + 0.15, 4), off) for _, c, on, off in MATRIX_REFS]),
        ("later", "Onsets 0.4 s late", "Outside the 0.2 s collar.",
         [(0, c, round(on + 0.4, 4), off) for _, c, on, off in MATRIX_REFS]),
        ("long", "One offset 1.5 s long", "The speech event ends at 15.5 s.", [s1, s2, (0, 1, 10.0, 15.5)]),
        ("split", "One event split", "Speech arrives as two pieces with a 0.5 s hole.",
         [s1, s2, (0, 1, 10.0, 11.75), (0, 1, 12.25, 14.0)]),
        ("merge", "Two events merged", "Both sirens arrive as one detection.", [(0, 0, 2.0, 7.0), sp]),
        ("alarm", "One false alarm", "An extra half second of speech.", [s1, s2, sp, (0, 1, 17.0, 17.5)]),
        ("miss", "One event missed", "The second siren is never reported.", [s1, sp]),
        ("class", "Wrong class", "The speech event is labelled siren.", [s1, s2, (0, 0, 10.0, 14.0)]),
    ]


MATRIX_COLUMNS = [
        metric("event_f1", "Event F1"), metric("segment_f1", "Segment F1"),
        metric("error_rate", "Segment ER", lower_is_better=True), metric("frame_f1", "Frame F1"),
        metric("psds1", "PSDS1"), metric("psds2", "PSDS2"),
]
MATRIX_CLIP, MATRIX_EXPOSURE = 20.0, 600.0


def score_all(preds):
    """The six headline scores of one list of predicted events against the shared references."""
    clip, exposure = MATRIX_CLIP, MATRIX_EXPOSURE
    bounds = steps(0.0, clip, 0.05)
    event = sm.event.f1(MATRIX_REFS, preds, recordings={0: clip})
    segment = sm.segment.f1(MATRIX_REFS, preds, recordings={0: clip})
    columns_by_class = {}
    for c in (0, 1):
        labels = frame_labels(preds, 0, clip, c, bounds)
        columns_by_class[c] = [1.0 if x else 0.0 for x in labels]
    frames = sm.frame.events(MATRIX_REFS, {0: (bounds, columns_by_class)},
                             recordings={0: clip}, threshold=0.5)
    quiet, quiet_durations = silent_recordings(1, exposure - clip, round((exposure - clip) / clip), (0, 1))
    scores = {0: (bounds, columns_by_class), **quiet}
    durations = {0: clip, **quiet_durations}
    one = run_psds(MATRIX_REFS, scores, durations, PSDS1)
    two = run_psds(MATRIX_REFS, scores, durations, PSDS2)
    return {
        "event_f1": r(event.f1), "segment_f1": r(segment.f1), "error_rate": r(segment.error_rate),
        "frame_f1": r(frames["micro"]["f1"]), "psds1": r(one.psds), "psds2": r(two.psds),
    }


def events_timeline(preds, collars=False):
    """Neutral states: the six metrics judge the same events differently."""
    timeline = {
        "domain": [0, MATRIX_CLIP],
        "rows": [
            interval_row("Reference", MATRIX_REFS, ["ref"] * len(MATRIX_REFS)),
            interval_row("Prediction", preds, ["plain"] * len(preds)),
        ],
    }
    if collars:
        timeline["bands"] = [{"a": r(on - COLLAR), "b": r(on + COLLAR)} for _, _, on, _ in MATRIX_REFS]
    return timeline


def hero_figure():
    """The home page control: the whole detector arrives late by a chosen delay."""
    frames = []
    for delay in steps(0.0, 2.0, 0.05):
        preds = [(0, c, round(on + delay, 4), round(off + delay, 4)) for _, c, on, off in MATRIX_REFS]
        values = score_all(preds)
        if values["event_f1"] == 1.0:
            note = "Inside the 0.2 s onset collar. Event F1 does not notice."
        elif values["psds1"] == 1.0:
            note = "Past the collar every event fails, so event F1 is zero. PSDS still accepts the overlap."
        elif values["psds1"] > 0:
            note = "PSDS1 now misses the short events: less than 70% of them is covered."
        else:
            note = "No event is 70% covered any more. PSDS2, which asks for 10%, still scores."
        frames.append({"value": delay, "timeline": events_timeline(preds, collars=True),
                       "scores": values, "note": note})
    return {"id": "hero", "columns": MATRIX_COLUMNS, "start": 8, "frames": frames,
            "control": {"label": "Delay every detection", "unit": "s late"}}


def matrix_figure():
    columns = MATRIX_COLUMNS
    rows = [
        {"id": ident, "label": label, "detail": detail, "scores": score_all(preds),
         "timeline": events_timeline(preds)}
        for ident, label, detail, preds in matrix_predictions()
    ]
    return {"id": "matrix", "columns": columns, "rows": rows,
            "setup": {"clipSeconds": MATRIX_CLIP, "exposureSeconds": MATRIX_EXPOSURE, "frameSeconds": 0.05,
                      "segmentSeconds": 1.0}}


FIGURES = {
    "hero": hero_figure,
    "matrix": matrix_figure,
    "event_f1": event_figure,
    "segment_f1": segment_figure,
    "frame": frame_figure,
    "brier": brier_figure,
    "psds": psds_figure,
    "pipsds": pipsds_figure,
    "streaming": streaming_figure,
}


def same(left, right) -> bool:
    if isinstance(left, float) or isinstance(right, float):
        return isinstance(left, (int, float)) and isinstance(right, (int, float)) and abs(left - right) <= 2e-6
    if isinstance(left, dict):
        return isinstance(right, dict) and left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return isinstance(right, list) and len(left) == len(right) and all(map(same, left, right))
    return left == right


def stale_figures(directory: Path = OUT) -> list[str]:
    """Names of figure files that no longer match what the library computes."""
    stale = []
    for name, build in FIGURES.items():
        path = directory / f"{name}.json"
        fresh = json.loads(json.dumps(build()))
        if not path.exists() or not same(json.loads(path.read_text(encoding="utf-8")), fresh):
            stale.append(path.name)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the committed files instead of writing")
    args = parser.parse_args(argv)
    if args.check:
        stale = stale_figures()
        if stale:
            print("out of date: " + ", ".join(stale), file=sys.stderr)
            return 1
        print(f"{len(FIGURES)} figure files match the library")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in FIGURES.items():
        text = json.dumps(build(), separators=(",", ":"), allow_nan=False)
        (OUT / f"{name}.json").write_text(text + "\n", encoding="utf-8")
        print(f"{name}.json {len(text) / 1024:.1f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
