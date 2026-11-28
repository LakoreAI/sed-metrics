#!/usr/bin/env python3
# /// script
# requires-python = "==3.12.*"
# dependencies = [
#   "sedmetrics==0.1.1",
#   "torch==2.7.1",
#   "torchaudio==2.7.1",
#   "torchvision==0.22.1",
#   "timm==1.0.15",
#   "einops==0.8.2",
#   "nnAudio==0.3.4",
#   "transformers==4.57.6",
#   "numpy==1.26.4",
#   "scipy==1.17.1",
#   "soundfile==0.14.0",
#   "soxr==1.1.0",
#   "pyarrow==25.0.1",
# ]
# ///
"""Compare pretrained sound event detectors with SEDMetrics.

Five AudioSet Strong checkpoints from PretrainedSED (Schmid et al., ICASSP
2025) are run on two datasets and scored with the published ``sedmetrics``
package. See ``benchmarks/README.md`` for the protocol.

    uv run benchmarks/compare_models.py fetch    --dataset audioset-strong
    uv run benchmarks/compare_models.py predict  --dataset urban-sed --urban-sed DIR
    uv run benchmarks/compare_models.py evaluate --dataset urban-sed
    uv run benchmarks/compare_models.py report

Everything downloaded or produced goes to ``--work-dir`` (default
``benchmarks/runs``, which git ignores).
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import math
import os
import platform
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

UPSTREAM_URL = "https://github.com/fschmid56/PretrainedSED.git"
UPSTREAM_COMMIT = "1aa47e482f7e89904cba2338999345025d8b4e36"
CHECKPOINT_URL = "https://github.com/fschmid56/PretrainedSED/releases/download/v0.0.1/{}.pt"

# name -> (checkpoint, sha256, PSDS1 on AudioSet Strong eval as published upstream)
MODELS = {
    "ATST-F": (
        "ATST-F_strong_1",
        "fbf2577958e3648d55ee8cea7e0e5260c4505fb0c13964e1ec81bc367cee5eda",
        45.8,
    ),
    "BEATs": (
        "BEATs_strong_1",
        "db13a79ae90a0cfd0f9911a6a1d8cdb89324322bee642dcfe32de022123b8b54",
        46.5,
    ),
    "fPaSST": (
        "fpasst_strong_1",
        "49b8d30f8d09ea92840d477df6092533cb86ecc7a2bc9e5c11d85e68233fb6ef",
        45.4,
    ),
    "M2D": (
        "M2D_strong_1",
        "5b467fe2980f90b7f6ee720440f8e87110f7a0cdf627376a32d80816b1a8e58a",
        46.3,
    ),
    # The upstream results table does not list the low-complexity model.
    "frame_mn10": (
        "frame_mn10_strong_1",
        "4a0fe320d5369987b772394c51881fb20a602967e6842f72f3e5c8181065ece7",
        None,
    ),
}

AUDIOSET_REPO = "CLAPv2/audioset_strong"
AUDIOSET_REVISION = "a27114f2c3b6cfe51ee1b4435c295c40d919b8ee"

SAMPLE_RATE = 16_000
CLIP_SECONDS = 10.0
N_FRAMES = 250
FRAME_SECONDS = CLIP_SECONDS / N_FRAMES

# URBAN-SED class -> AudioSet Strong classes. Fixed before any result was seen:
# the class with the same meaning, plus narrower classes naming the same sound.
# A clip frame gets the maximum score over the listed classes.
URBAN_SED_MAPPING = {
    "air_conditioner": ["Air conditioning"],
    "car_horn": ["Vehicle horn, car horn, honking, toot"],
    "children_playing": ["Children playing"],
    "dog_bark": ["Bark", "Yip", "Bow-wow"],
    "drilling": ["Drill"],
    "engine_idling": ["Idling"],
    "gun_shot": [
        "Gunshot, gunfire",
        "Machine gun",
        "Fusillade",
        "Artillery fire",
        "Cap gun",
    ],
    "jackhammer": ["Jackhammer"],
    "siren": [
        "Siren",
        "Civil defense siren",
        "Police car (siren)",
        "Ambulance (siren)",
        "Fire engine, fire truck (siren)",
    ],
    "street_music": ["Music"],
}

MEDIAN_WINDOW = 9
PIPSDS_WINDOWS = (1, 5, 9, 15, 25)
THRESHOLD_GRID = [0.01, 0.02, 0.03, 0.04] + [round(0.05 * i, 2) for i in range(1, 20)]
AUDIOSET_THRESHOLDS = (0.1, 0.2, 0.5)


# --- small helpers ------------------------------------------------------------


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, target: Path, sha256: str, attempts: int = 4) -> None:
    """Download ``url`` to ``target`` and verify its checksum."""
    if target.exists() and sha256_of(target) == sha256:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as out:
                while block := response.read(1 << 20):
                    out.write(block)
            found = sha256_of(part)
            if found != sha256:
                raise OSError(f"checksum mismatch for {target.name}: {found}")
            part.replace(target)
            return
        except OSError as error:
            if attempt == attempts:
                raise
            log(f"retry {attempt} for {target.name}: {error}")
            time.sleep(5 * attempt)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def frame_boundaries(duration: float) -> list[float]:
    """Frame edges of the 40 ms model output, ending exactly at ``duration``."""
    n = min(N_FRAMES, max(1, math.ceil(duration / FRAME_SECONDS - 1e-9)))
    return [i / (N_FRAMES / CLIP_SECONDS) for i in range(n)] + [duration]


# --- fetch --------------------------------------------------------------------


def upstream_dir(work: Path) -> Path:
    return work / "upstream" / "PretrainedSED"


def fetch_upstream(work: Path) -> Path:
    target = upstream_dir(work)
    if not (target / ".git").is_dir():
        target.mkdir(parents=True, exist_ok=True)
        run = lambda *args: subprocess.run(["git", "-C", str(target), *args], check=True)
        run("init", "-q")
        run("remote", "add", "origin", UPSTREAM_URL)
        run("fetch", "-q", "--depth", "1", "origin", UPSTREAM_COMMIT)
        run("checkout", "-q", "FETCH_HEAD")
    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if head != UPSTREAM_COMMIT:
        raise SystemExit(f"{target} is at {head}, expected {UPSTREAM_COMMIT}")
    return target


def fetch_checkpoints(work: Path, models: list[str]) -> None:
    for name in models:
        checkpoint, checksum, _ = MODELS[name]
        log(f"checkpoint {checkpoint}")
        download(CHECKPOINT_URL.format(checkpoint), work / "checkpoints" / f"{checkpoint}.pt", checksum)


def audioset_dir(work: Path) -> Path:
    return work / "data" / "audioset_strong_eval"


def fetch_audioset(work: Path, limit_batches: int | None) -> None:
    url = (
        f"https://huggingface.co/api/datasets/{AUDIOSET_REPO}/tree/"
        f"{AUDIOSET_REVISION}/data/test?limit=1000"
    )
    with urllib.request.urlopen(url, timeout=120) as response:
        if response.headers.get("Link"):
            raise SystemExit("the file listing is paginated; extend fetch_audioset")
        listing = json.load(response)
    files = sorted(
        (item for item in listing if item["path"].endswith(".parquet")),
        key=lambda item: item["path"],
    )
    if limit_batches:
        files = files[:limit_batches]
    total = sum(item["size"] for item in files)
    log(f"AudioSet Strong eval: {len(files)} files, {total / 1e9:.1f} GB")
    base = f"https://huggingface.co/datasets/{AUDIOSET_REPO}/resolve/{AUDIOSET_REVISION}/"
    done = 0

    def one(item):
        name = Path(item["path"]).name
        download(base + item["path"], audioset_dir(work) / name, item["lfs"]["oid"])
        return item["size"]

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index, size in enumerate(pool.map(one, files), start=1):
            done += size
            if index % 50 == 0 or index == len(files):
                rate = done / (time.perf_counter() - start) / 1e6
                log(f"  {index}/{len(files)} files, {done / 1e9:.1f} GB, {rate:.1f} MB/s")


# --- datasets -----------------------------------------------------------------


def upstream_literal(source: Path, name: str):
    """Read a top-level literal assignment from an upstream file without importing it."""
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise SystemExit(f"{name} not found in {source}")


def train_classes(work: Path) -> list[str]:
    source = upstream_dir(work) / "data_util" / "audioset_classes.py"
    return upstream_literal(source, "as_strong_train_classes")


def prepare_urban_sed(root: Path, split: str, limit: int | None):
    from sedmetrics.adapters import load_urban_sed

    dataset = load_urban_sed(root, split=split, limit=limit)
    names = sorted(dataset.class_names.values())
    if names != sorted(URBAN_SED_MAPPING):
        raise SystemExit(f"unexpected URBAN-SED classes: {names}")
    class_index = {class_id: names.index(name) for class_id, name in dataset.class_names.items()}
    ids = [dataset.recording_names[i] for i in range(len(dataset.recording_names))]
    # Some offsets are stored as 10.000000000000002 s. Left alone they open an
    # eleventh 1 s segment, so times are rounded to microseconds.
    meta = {
        "ids": ids,
        "durations": [round(dataset.durations[i], 6) for i in range(len(ids))],
        "references": [
            [r, class_index[c], round(onset, 6), round(offset, 6)]
            for r, c, onset, offset in dataset.references
        ],
        "classes": names,
    }
    root = Path(root).expanduser()
    if not (root / "audio").is_dir():
        root = root / "URBAN-SED_v2.0.0"

    def audio():
        for clip in ids:
            yield root / "audio" / split / f"{clip}.wav"

    return meta, audio


def merge_intervals(events: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping or touching intervals, as the upstream evaluation does."""
    merged: list[tuple[float, float]] = []
    for onset, offset in sorted(events):
        if merged and merged[-1][1] >= onset:
            merged[-1] = (merged[-1][0], max(merged[-1][1], offset))
        else:
            merged.append((onset, offset))
    return merged


def merge_references(references) -> list[tuple]:
    """Join overlapping or touching events of one class in one clip.

    ``sed_scores_eval`` requires this of PSDS ground truth.
    """
    groups: dict[tuple, list] = {}
    for recording, class_id, onset, offset in references:
        groups.setdefault((recording, class_id), []).append((onset, offset))
    return [
        (recording, class_id, onset, offset)
        for (recording, class_id), events in sorted(groups.items())
        for onset, offset in merge_intervals(events)
    ]


def prepare_audioset(work: Path, limit: int | None):
    """Ground truth following the upstream evaluation: train classes only,
    same-class overlaps merged, clips without any event dropped."""
    import pyarrow.parquet as parquet
    from sedmetrics.adapters import parse_audioset_strong_events

    upstream = upstream_dir(work)
    description = upstream_literal(upstream / "hf_dataset_gen" / "audioset_strong.py", "_DESCRIPTION")
    table = description.split("++labels_strong++")[1].split("++labels_weak++")[0]
    mid_name = dict(entry.split("::", 1) for entry in table.split(";;"))
    vocabulary = set(train_classes(work))
    with (upstream / "resources" / "eval_durations.csv").open(newline="") as handle:
        official = {name[1:]: float(duration) for name, duration in csv.reader(handle)}

    files = sorted(audioset_dir(work).glob("*.parquet"))
    if not files:
        raise SystemExit("no AudioSet parquet files; run `fetch --dataset audioset-strong`")

    clips = []  # (id, file index, row index, {name: intervals})
    seen: set[str] = set()
    counts = {"rows": 0, "not_in_official_list": 0, "without_events": 0,
              "events_outside_vocabulary": 0}
    for file_index, path in enumerate(files):
        columns = parquet.read_table(path, columns=["index", "raw_text"]).to_pylist()
        for row_index, row in enumerate(columns):
            counts["rows"] += 1
            # e.g. "fsx_..._audioset_strong_processed_eval_<video id>"
            clip = row["index"].split("_processed_eval_", 1)[-1]
            if clip not in official:
                counts["not_in_official_list"] += 1
                continue
            if clip in seen:
                raise SystemExit(f"duplicate clip {clip}")
            seen.add(clip)
            by_class: dict[str, list[tuple[float, float]]] = {}
            for onset, offset, _, mid in parse_audioset_strong_events(row["raw_text"]):
                name = mid_name.get(mid)
                if name not in vocabulary:
                    counts["events_outside_vocabulary"] += 1
                    continue
                by_class.setdefault(name, []).append((onset, offset))
            if not by_class:
                counts["without_events"] += 1
                continue
            clips.append((clip, file_index, row_index, by_class))
            if limit and len(clips) >= limit:
                break
        if limit and len(clips) >= limit:
            break

    if counts["not_in_official_list"] > counts["rows"] // 2:
        raise SystemExit(f"clip ids do not match the official evaluation list: {counts}")
    classes = sorted({name for *_, by_class in clips for name in by_class})
    class_index = {name: i for i, name in enumerate(classes)}
    references, durations = [], []
    for recording, (clip, _, _, by_class) in enumerate(clips):
        duration = official[clip]
        for name, intervals in sorted(by_class.items()):
            for onset, offset in merge_intervals(intervals):
                references.append([recording, class_index[name], onset, offset])
                duration = max(duration, offset)
        durations.append(duration)
    counts["official_list_size"] = len(official)
    meta = {
        "ids": [clip for clip, *_ in clips],
        "durations": durations,
        "references": references,
        "classes": classes,
        "selection": counts,
    }
    wanted: dict[int, list[int]] = {}
    for _, file_index, row_index, _ in clips:
        wanted.setdefault(file_index, []).append(row_index)

    def audio():
        for file_index in sorted(wanted):
            column = parquet.read_table(files[file_index], columns=["audio"]).column("audio")
            for row_index in wanted[file_index]:
                yield column[row_index].as_py()["bytes"]

    return meta, audio


def load_waveform(source) -> np.ndarray:
    """Mono 16 kHz audio, padded or cut to one 10 s model input."""
    import soundfile
    import soxr

    handle = io.BytesIO(source) if isinstance(source, bytes) else source
    samples, rate = soundfile.read(handle, dtype="float32", always_2d=True)
    samples = samples.mean(axis=1)
    if rate != SAMPLE_RATE:
        samples = soxr.resample(samples, rate, SAMPLE_RATE, quality="HQ")
    length = int(CLIP_SECONDS * SAMPLE_RATE)
    out = np.zeros(length, dtype=np.float32)
    out[: min(length, len(samples))] = samples[:length]
    return out


# --- predict ------------------------------------------------------------------


def build_model(work: Path, name: str):
    repo = str(upstream_dir(work))
    if repo not in sys.path:
        sys.path.insert(0, repo)
    import models.prediction_wrapper as wrapper

    wrapper.RESOURCES_FOLDER = str((work / "checkpoints").resolve())
    checkpoint = MODELS[name][0]
    extra = {}
    if name == "BEATs":
        from models.beats.BEATs_wrapper import BEATsWrapper

        base = BEATsWrapper()
    elif name == "ATST-F":
        from models.atstframe.ATSTF_wrapper import ATSTWrapper

        base = ATSTWrapper()
    elif name == "fPaSST":
        from models.frame_passt.fpasst_wrapper import FPaSSTWrapper

        base = FPaSSTWrapper()
    elif name == "M2D":
        from models.m2d.M2D_wrapper import M2DWrapper

        base = M2DWrapper()
        extra["embed_dim"] = base.m2d.cfg.feature_d
    else:
        from models.frame_mn.Frame_MN_wrapper import FrameMNWrapper
        from models.frame_mn.utils import NAME_TO_WIDTH

        base = FrameMNWrapper(NAME_TO_WIDTH(name))
        extra["embed_dim"] = base.state_dict()["frame_mn.features.16.1.bias"].shape[0]
    return wrapper.PredictionsWrapper(base, checkpoint=checkpoint, **extra).eval()


def pick_device(requested: str):
    import torch

    if requested != "auto":
        return torch.device(requested)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def score_dir(work: Path, tag: str) -> Path:
    return work / "scores" / tag


def predict(work: Path, tag: str, meta, audio, columns: list[str], dtype: str,
            models: list[str], batch_size: int, device_name: str) -> None:
    """Write sigmoid scores as a [classes, clips, frames] array per model."""
    import torch

    out_dir = score_dir(work, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "meta.json"
    meta = {**meta, "score_columns": columns, "score_dtype": dtype}
    if meta_path.exists() and read_json(meta_path) != json.loads(json.dumps(meta)):
        raise SystemExit(f"{meta_path} describes a different run; delete {out_dir} first")
    write_json(meta_path, meta)

    vocabulary = train_classes(work)
    source = [vocabulary.index(name) for name in columns]
    n_clips = len(meta["ids"])
    device = pick_device(device_name)

    for name in models:
        target = out_dir / f"{name}.npy"
        if target.exists():
            log(f"{tag} {name}: scores exist, skipping")
            continue
        torch.manual_seed(0)
        model = build_model(work, name)
        parameters = sum(p.numel() for p in model.parameters())
        part = out_dir / f"{name}.part.npy"
        scores = np.lib.format.open_memmap(
            part, mode="w+", dtype=dtype, shape=(len(columns), n_clips, N_FRAMES)
        )

        def forward(batch, on):
            with torch.inference_mode():
                logits, _ = model(model.mel_forward(batch.to(on)))
                return torch.sigmoid(logits.float())

        def synchronise():
            if device.type == "mps":
                torch.mps.synchronize()
            elif device.type == "cuda":
                torch.cuda.synchronize()

        seconds, position, check = 0.0, 0, None
        started = time.perf_counter()

        def batches():
            pending = []
            with ThreadPoolExecutor(max_workers=6) as pool:
                for item in audio():
                    pending.append(pool.submit(load_waveform, item))
                    if len(pending) == batch_size:
                        yield np.stack([future.result() for future in pending])
                        pending = []
                if pending:
                    yield np.stack([future.result() for future in pending])

        for array in batches():
            batch = torch.from_numpy(array)
            if position == 0:
                # Agreement between the accelerator and the CPU on real clips.
                reference = forward(batch[:4], torch.device("cpu"))
                model.to(device)
                check = float((forward(batch[:4], device).cpu() - reference).abs().max())
                forward(batch, device)  # warm-up, not timed
                synchronise()
            clock = time.perf_counter()
            probabilities = forward(batch, device)
            synchronise()
            seconds += time.perf_counter() - clock
            selected = probabilities[:, source, :].cpu().numpy()
            if not np.isfinite(selected).all():
                raise SystemExit(f"{name}: non-finite scores in batch at clip {position}")
            end = position + len(array)
            scores[:, position:end, :] = selected.transpose(1, 0, 2)
            if (position // batch_size) % 25 == 0:
                log(f"{tag} {name}: {end}/{n_clips} clips, {seconds / end * 1000:.1f} ms/clip")
            position = end
        if position != n_clips:
            raise SystemExit(f"{name}: read {position} clips, expected {n_clips}")
        scores.flush()
        del scores
        part.replace(target)
        write_json(out_dir / f"{name}.json", {
            "model": name,
            "checkpoint": MODELS[name][0],
            "parameters": parameters,
            "device": device.type,
            "batch_size": batch_size,
            "clips": n_clips,
            "forward_seconds": seconds,
            "milliseconds_per_clip": seconds / n_clips * 1000,
            "wall_seconds": time.perf_counter() - started,
            "max_abs_difference_cpu_vs_device_4_clips": check,
        })
        log(f"{tag} {name}: done, device/CPU max difference {check:.2e}")
        del model
        if device.type == "mps":
            torch.mps.empty_cache()


# --- evaluate -----------------------------------------------------------------


def median(scores: np.ndarray, window: int) -> np.ndarray:
    """Median filter along time (last axis), as in the upstream decoding."""
    from scipy.ndimage import median_filter

    if window <= 1:
        return scores
    size = (1,) * (scores.ndim - 1) + (window,)
    return median_filter(scores, size=size)


def decode(scores: np.ndarray, threshold: float, class_id: int, durations) -> list[tuple]:
    """Runs of frames with score > threshold, as events. ``scores`` is [clips, frames]."""
    active = np.zeros((scores.shape[0], scores.shape[1] + 2), dtype=np.int8)
    active[:, 1:-1] = scores > threshold
    change = np.diff(active, axis=1)
    clips, starts = np.nonzero(change == 1)
    _, ends = np.nonzero(change == -1)
    events = []
    for clip, start, end in zip(clips.tolist(), starts.tolist(), ends.tolist()):
        onset = start * FRAME_SECONDS
        offset = min(end * FRAME_SECONDS, durations[clip])
        if offset > onset:
            events.append((clip, class_id, onset, offset))
    return events


def score_tracks(scores: np.ndarray, durations) -> dict:
    """[classes, clips, frames] -> the mapping accepted by ``sedmetrics``."""
    tracks = {}
    for clip, duration in enumerate(durations):
        boundaries = frame_boundaries(duration)
        frames = len(boundaries) - 1
        tracks[clip] = (
            boundaries,
            {c: scores[c, clip, :frames].tolist() for c in range(scores.shape[0])},
        )
    return tracks


PSDS_PROFILES = {
    "psds1": dict(dtc_threshold=0.7, gtc_threshold=0.7, cttc_threshold=None, alpha_ct=0.0),
    "psds2": dict(dtc_threshold=0.1, gtc_threshold=0.1, cttc_threshold=0.3, alpha_ct=0.5),
}


def urban_scores(work: Path, split: str, model: str):
    """Mapped, unfiltered [10, clips, frames] scores for one URBAN-SED split."""
    directory = score_dir(work, f"urban-sed-{split}")
    meta = read_json(directory / "meta.json")
    raw = np.load(directory / f"{model}.npy")
    column = {name: i for i, name in enumerate(meta["score_columns"])}
    mapped = np.stack([
        raw[[column[source] for source in URBAN_SED_MAPPING[target]]].max(axis=0)
        for target in meta["classes"]
    ])
    return meta, mapped


def evaluate_urban(work: Path, model: str) -> None:
    import sedmetrics as sm

    timings: dict[str, float] = {}

    def timed(label, function, *args, **kwargs):
        clock = time.perf_counter()
        value = function(*args, **kwargs)
        timings[label] = timings.get(label, 0.0) + time.perf_counter() - clock
        return value

    # Thresholds are chosen per class on the validation split.
    meta, mapped = urban_scores(work, "validate", model)
    filtered = median(mapped, MEDIAN_WINDOW)
    durations = dict(enumerate(meta["durations"]))
    chosen = {"event_f1": [], "segment_f1": []}
    for c in range(len(meta["classes"])):
        references = [tuple(r) for r in meta["references"] if r[1] == c]
        best = {"event_f1": (-1.0, None), "segment_f1": (-1.0, None)}
        for threshold in THRESHOLD_GRID:
            events = decode(filtered[c], threshold, c, meta["durations"])
            for metric, function in (("event_f1", sm.event.f1), ("segment_f1", sm.segment.f1)):
                value = function(references, events, recordings=durations).f1 or 0.0
                if value > best[metric][0]:
                    best[metric] = (value, threshold)
        for metric in best:
            chosen[metric].append(best[metric][1])

    meta, mapped = urban_scores(work, "test", model)
    classes = meta["classes"]
    durations = dict(enumerate(meta["durations"]))
    references = [tuple(r) for r in meta["references"]]
    filtered = median(mapped, MEDIAN_WINDOW)
    result: dict = {
        "model": model, "dataset": "urban-sed", "split": "test",
        "clips": len(meta["ids"]), "reference_events": len(references),
        "audio_hours": sum(meta["durations"]) / 3600, "classes": classes,
        "median_window_frames": MEDIAN_WINDOW, "validation_thresholds": chosen,
    }

    # Event decisions: fixed 0.5 and validation-tuned thresholds.
    for label, thresholds in (("fixed_0.5", None), ("tuned", chosen)):
        block = {}
        for metric in ("event_f1", "segment_f1", "event_f1_onset_only"):
            source = "event_f1" if metric.startswith("event") else metric
            events = []
            for c in range(len(classes)):
                threshold = 0.5 if thresholds is None else thresholds[source][c]
                events += decode(filtered[c], threshold, c, meta["durations"])
            for average in ("micro", "macro"):
                if metric == "segment_f1":
                    value = timed("segment_f1", sm.segment.f1, references, events,
                                  recordings=durations, average=average)
                else:
                    value = timed("event_f1", sm.event.f1, references, events,
                                  recordings=durations, average=average,
                                  evaluate_offset=metric == "event_f1")
                block[f"{metric}_{average}"] = value.to_dict()
        result[label] = block

    # What a frame detector with no error would score against these annotations:
    # overlapping events of one class become a single detection.
    oracle = []
    for clip, c, onset, offset in merge_references(references):
        start = math.floor(onset / FRAME_SECONDS + 0.5)
        end = math.floor(offset / FRAME_SECONDS + 0.5)
        if end > start:
            oracle.append((clip, c, start * FRAME_SECONDS, end * FRAME_SECONDS))
    result["frame_oracle"] = {
        "event_f1_macro": sm.event.f1(references, oracle, recordings=durations,
                                      average="macro").f1,
        "segment_f1_macro": sm.segment.f1(references, oracle, recordings=durations,
                                          average="macro").f1,
    }

    # Threshold-free scores.
    psds_references = merge_references(references)
    result["psds_reference_events"] = len(psds_references)
    tracks = timed("convert_tracks", score_tracks, filtered, meta["durations"])
    for profile, options in PSDS_PROFILES.items():
        value = timed(profile, sm.psds.psds, psds_references, tracks,
                      recordings=durations, **options)
        result[profile] = {
            "psds": value.psds,
            "classes": {classes[item.class_id]: item.psds for item in value.classes},
            "curve": {"efpr": value.efpr, "tpr": value.tpr},
        }
        log(f"{model} {profile} = {value.psds:.4f}")

    frame = timed("frame_events", sm.frame.events, references, tracks,
                  recordings=durations, threshold=0.5)
    result["frame"] = {
        "macro": frame["macro"],
        "classes": {
            classes[c]: {k: v[k] for k in ("average_precision", "auroc")}
            for c, v in frame["classes"].items()
        },
    }

    # Brier score on unfiltered probabilities; a frame is a positive target when
    # it overlaps a reference event, matching the frame metrics' mapping.
    targets = np.zeros(mapped.shape, dtype=np.float32)
    for clip, c, onset, offset in references:
        boundaries = np.asarray(frame_boundaries(durations[clip]))
        overlap = (np.minimum(boundaries[1:], offset) - np.maximum(boundaries[:-1], onset)) > 0
        targets[c, clip, : len(overlap)][overlap] = 1.0
    brier = {}
    for c, name in enumerate(classes):
        brier[name] = timed("brier", sm.frame.brier, targets[c].ravel().tolist(),
                            mapped[c].ravel().tolist())
    result["brier"] = {
        "macro": float(np.mean([value["brier"] for value in brier.values()])),
        "classes": {name: value["brier"] for name, value in brier.items()},
    }

    # piPSDS over median-filter lengths.
    processed = {f"median_{w}": score_tracks(median(mapped, w), meta["durations"])
                 for w in PIPSDS_WINDOWS}
    for profile, options in PSDS_PROFILES.items():
        value = timed(f"pipsds_{profile}", sm.psds.pipsds, psds_references, processed,
                      recordings=durations, **options)
        singles = {
            label: sm.psds.psds(psds_references, scores, recordings=durations, **options).psds
            for label, scores in processed.items()
        }
        result[f"pi{profile}"] = {"psds": value.psds, "single_postprocessing": singles}
        log(f"{model} pi{profile} = {value.psds:.4f}")

    result["metric_seconds"] = timings
    write_json(work / "results" / "urban-sed" / f"{model}.json", result)


def _class_psds(task):
    """PSDS of one class. Used in worker processes."""
    import sedmetrics as sm

    directory, model, column, references, durations = task
    scores = np.load(Path(directory) / f"{model}.npy", mmap_mode="r")
    values = median(np.array(scores[column], dtype=np.float32), MEDIAN_WINDOW)[None]
    tracks = score_tracks(values, durations)
    clock = time.perf_counter()
    result = sm.psds.psds(
        [(r, 0, onset, offset) for r, _, onset, offset in references],
        tracks, recordings=dict(enumerate(durations)),
        alpha_st=0.0, **PSDS_PROFILES["psds1"],
    )
    return column, result.psds, time.perf_counter() - clock


def evaluate_audioset(work: Path, model: str, workers: int, limit_tag: str) -> None:
    import sedmetrics as sm

    directory = score_dir(work, limit_tag)
    meta = read_json(directory / "meta.json")
    classes = meta["classes"]
    if meta["score_columns"] != classes:
        raise SystemExit("score columns do not match the evaluated classes")
    durations = meta["durations"]
    by_class: list[list] = [[] for _ in classes]
    for reference in meta["references"]:
        by_class[reference[1]].append(reference)

    clock = time.perf_counter()
    tasks = [(str(directory), model, c, by_class[c], durations) for c in range(len(classes))]
    values, core_seconds = {}, 0.0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for done, (column, value, seconds) in enumerate(pool.map(_class_psds, tasks), start=1):
            values[classes[column]] = value
            core_seconds += seconds
            if done % 50 == 0 or done == len(tasks):
                log(f"{model} per-class PSDS1: {done}/{len(tasks)}")
    psds_wall = time.perf_counter() - clock
    macro = float(np.mean(list(values.values())))
    log(f"{model} macro-averaged PSDS1 = {macro:.4f}")

    result = {
        "model": model, "dataset": "audioset-strong", "split": "eval",
        "clips": len(meta["ids"]), "reference_events": len(meta["references"]),
        "audio_hours": sum(durations) / 3600, "n_classes": len(classes),
        "selection": meta["selection"], "median_window_frames": MEDIAN_WINDOW,
        "psds1_macro_averaged": macro, "psds1_classes": values,
        "published_psds1": MODELS[model][2],
    }

    scores = np.load(directory / f"{model}.npy", mmap_mode="r")
    events: dict[float, list] = {t: [] for t in AUDIOSET_THRESHOLDS}
    for c in range(len(classes)):
        filtered = median(np.array(scores[c], dtype=np.float32), MEDIAN_WINDOW)
        for threshold in AUDIOSET_THRESHOLDS:
            events[threshold] += decode(filtered, threshold, c, durations)
    references = [tuple(r) for r in meta["references"]]
    recordings = dict(enumerate(durations))
    seconds = {"psds1_per_class_wall": psds_wall, "psds1_per_class_core": core_seconds,
               "workers": workers}
    result["decisions"] = {}
    for threshold, predicted in events.items():
        block = {"predicted_events": len(predicted)}
        for metric, function in (("event_f1", sm.event.f1), ("segment_f1", sm.segment.f1)):
            for average in ("micro", "macro"):
                clock = time.perf_counter()
                value = function(references, predicted, recordings=recordings, average=average)
                key = f"{metric}_seconds_at_{threshold}"
                seconds[key] = seconds.get(key, 0.0) + time.perf_counter() - clock
                summary = value.to_dict()
                summary.pop("classes", None)
                block[f"{metric}_{average}"] = summary
        result["decisions"][str(threshold)] = block
        log(f"{model} threshold {threshold}: segment F1 "
            f"{block['segment_f1_micro']['f1']:.4f}, event F1 {block['event_f1_micro']['f1']:.4f}")
    result["metric_seconds"] = seconds
    write_json(work / "results" / limit_tag / f"{model}.json", result)


# --- report -------------------------------------------------------------------


def table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + " --- |" * len(headers)]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def report(work: Path) -> None:
    results = work / "results"
    sections = ["# Model comparison\n"]
    f3 = lambda value: "n/a" if value is None else f"{value:.3f}"

    def load(tag):
        return [read_json(results / tag / f"{m}.json") for m in MODELS
                if (results / tag / f"{m}.json").exists()]

    urban = load("urban-sed")
    if urban:
        sections.append(f"## URBAN-SED v2.0.0 test ({urban[0]['clips']} clips, zero-shot)\n")
        headers = ["Model", "PSDS1", "PSDS2", "piPSDS1", "piPSDS2",
                   "Event F1 (macro, tuned)", "Segment F1 (macro, tuned)", "Segment ER (tuned)",
                   "Event F1 (macro, 0.5)", "Segment F1 (macro, 0.5)", "mAP", "AUROC", "Brier"]
        rows = [[
            r["model"], f3(r["psds1"]["psds"]), f3(r["psds2"]["psds"]),
            f3(r["pipsds1"]["psds"]), f3(r["pipsds2"]["psds"]),
            f3(r["tuned"]["event_f1_macro"]["f1"]), f3(r["tuned"]["segment_f1_macro"]["f1"]),
            f3(r["tuned"]["segment_f1_micro"]["error_rate"]),
            f3(r["fixed_0.5"]["event_f1_macro"]["f1"]),
            f3(r["fixed_0.5"]["segment_f1_macro"]["f1"]),
            f3(r["frame"]["macro"]["average_precision"]), f3(r["frame"]["macro"]["auroc"]),
            f"{r['brier']['macro']:.4f}",
        ] for r in urban]
        sections.append(table(headers, rows))
        write_csv(results / "urban-sed.csv", headers, rows)
    for directory in sorted(results.glob("audioset-strong*")):
        audioset = load(directory.name)
        if not audioset:
            continue
        first = audioset[0]
        sections.append(f"## {directory.name}: {first['clips']} clips, {first['n_classes']} classes\n")
        headers = ["Model", "PSDS1 macro", "Published PSDS1"] + [
            f"{metric} micro at {t}" for t in AUDIOSET_THRESHOLDS
            for metric in ("Event F1", "Segment F1")
        ]
        rows = []
        for r in audioset:
            published = r["published_psds1"]
            row = [r["model"], f"{100 * r['psds1_macro_averaged']:.1f}",
                   "n/a" if published is None else f"{published:.1f}"]
            for t in AUDIOSET_THRESHOLDS:
                block = r["decisions"][str(t)]
                row += [f3(block["event_f1_micro"]["f1"]), f3(block["segment_f1_micro"]["f1"])]
            rows.append(row)
        sections.append(table(headers, rows))
        write_csv(results / f"{directory.name}.csv", headers, rows)

    runs = sorted(score_dir(work, "").glob("*/*.json"))
    rows = []
    for path in runs:
        if path.name == "meta.json":
            continue
        r = read_json(path)
        rows.append([path.parent.name, r["model"], f"{r['parameters'] / 1e6:.1f}", r["device"],
                     f"{r['milliseconds_per_clip']:.1f}",
                     f"{r['max_abs_difference_cpu_vs_device_4_clips']:.1e}"])
    if rows:
        sections.append("## Inference\n")
        headers = ["Run", "Model", "Parameters (M)", "Device", "ms per 10 s clip",
                   "Max score difference vs CPU"]
        sections.append(table(headers, rows))
        write_csv(results / "inference.csv", headers, rows)

    (results / "tables.md").write_text("\n".join(sections), encoding="utf-8")
    write_json(results / "environment.json", environment())
    log(f"wrote {results / 'tables.md'}")


def write_csv(path: Path, headers, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def environment() -> dict:
    from importlib.metadata import version

    chip = platform.processor()
    memory = None
    if sys.platform == "darwin":
        read = lambda key: subprocess.run(["sysctl", "-n", key], capture_output=True,
                                          text=True).stdout.strip()
        chip = read("machdep.cpu.brand_string")
        memory = int(read("hw.memsize")) / 2**30
    packages = ["sedmetrics", "torch", "torchaudio", "timm", "numpy", "scipy", "soxr"]
    return {
        "platform": platform.platform(), "processor": chip, "memory_gib": memory,
        "cpu_count": os.cpu_count(), "python": platform.python_version(),
        "packages": {name: version(name) for name in packages},
        "upstream_commit": UPSTREAM_COMMIT, "audioset_revision": AUDIOSET_REVISION,
        "checkpoints": {name: {"file": m[0], "sha256": m[1]} for name, m in MODELS.items()},
    }


# --- command line -------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("stage", choices=["fetch", "predict", "evaluate", "report"])
    parser.add_argument("--dataset", choices=["urban-sed", "audioset-strong"])
    parser.add_argument("--urban-sed", type=Path, help="extracted URBAN-SED_v2.0.0 directory")
    parser.add_argument("--models", nargs="+", choices=list(MODELS), default=list(MODELS))
    parser.add_argument("--work-dir", type=Path, default=HERE / "runs")
    parser.add_argument("--device", default="auto", help="auto, cpu, mps or cuda")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument("--limit", type=int, help="first N clips only (smoke test)")
    parser.add_argument("--limit-batches", type=int, help="fetch only the first N parquet files")
    args = parser.parse_args(argv)
    work = args.work_dir.resolve()
    if args.stage != "report" and not args.dataset:
        parser.error("--dataset is required")
    suffix = f"-first{args.limit}" if args.limit else ""

    if args.stage == "fetch":
        fetch_upstream(work)
        fetch_checkpoints(work, args.models)
        if args.dataset == "audioset-strong":
            fetch_audioset(work, args.limit_batches)
    elif args.stage == "predict":
        fetch_upstream(work)
        fetch_checkpoints(work, args.models)
        if args.dataset == "urban-sed":
            if not args.urban_sed:
                parser.error("--urban-sed is required")
            columns = sorted({name for names in URBAN_SED_MAPPING.values() for name in names})
            for split in ("validate", "test"):
                meta, audio = prepare_urban_sed(args.urban_sed, split, args.limit)
                predict(work, f"urban-sed-{split}{suffix}", meta, audio, columns, "float32",
                        args.models, args.batch_size, args.device)
        else:
            meta, audio = prepare_audioset(work, args.limit)
            log(f"{len(meta['ids'])} clips, {len(meta['classes'])} classes, {meta['selection']}")
            predict(work, f"audioset-strong{suffix}", meta, audio, meta["classes"], "float16",
                    args.models, args.batch_size, args.device)
    elif args.stage == "evaluate":
        for model in args.models:
            if args.dataset == "urban-sed":
                if args.limit:
                    parser.error("URBAN-SED evaluation needs the full splits")
                evaluate_urban(work, model)
            else:
                evaluate_audioset(work, model, args.workers, f"audioset-strong{suffix}")
    else:
        report(work)


if __name__ == "__main__":
    main()
