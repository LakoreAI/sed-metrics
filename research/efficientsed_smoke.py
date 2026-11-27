"""Engineering smoke check using locally cached public EfficientSED features.

Run with PYTHONPATH=python and an environment containing torch and numpy.
The YOLiO cache is derived from AudioSet Strong training shards; this is not a
held-out benchmark. No training, post-processing or threshold tuning is done.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np
import sklearn
import torch
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score

from sedmetrics import SEDMetrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--clips", type=int, default=10)
    parser.add_argument("--classes", type=int, default=3)
    args = parser.parse_args()
    if args.clips < 1 or args.classes < 1:
        parser.error("--clips and --classes must be positive")

    checkpoint_hash = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    manifest = json.loads((args.cache / "manifest.json").read_text())
    if (manifest.get("checkpoint_sha256") != checkpoint_hash
            or manifest.get("encoder") != "EfficientSED fmn10+tf256 strong"
            or manifest.get("fps") != 25 or manifest.get("feature_dim") != 256
            or manifest.get("partial") is not False):
        raise ValueError("cached feature provenance does not match the selected checkpoint")

    module_path = args.upstream / "data_util" / "audioset_classes.py"
    spec = importlib.util.spec_from_file_location("efficientsed_classes", module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load class vocabulary from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    vocabulary = module.as_strong_train_classes
    if len(vocabulary) != 447 or len(set(vocabulary)) != 447:
        raise ValueError("unexpected upstream class vocabulary")
    paths = sorted((args.cache / "val" / "features").glob("*.npy"))[:args.clips]
    if len(paths) != args.clips:
        raise ValueError("not enough cached validation features")
    ids = {path.stem: index for index, path in enumerate(paths)}
    with (args.cache / "val" / "events.tsv").open(newline="") as handle:
        rows = [row for row in csv.DictReader(handle, delimiter="\t") if row["clip"] in ids]
    counts = Counter(row["label"] for row in rows if row["label"] in vocabulary)
    labels = [name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:args.classes]]
    if len(labels) != args.classes:
        raise ValueError("not enough referenced model classes in selected recordings")
    class_ids = {name: index for index, name in enumerate(labels)}
    refs = [(ids[row["clip"]], class_ids[row["label"]], float(row["onset"]), float(row["offset"]))
            for row in rows if row["label"] in class_ids]
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    weight = checkpoint["net.strong_head.weight"]
    bias = checkpoint["net.strong_head.bias"]
    if tuple(weight.shape) != (447, 256) or tuple(bias.shape) != (447,):
        raise ValueError("checkpoint head dimensions do not match EfficientSED fmn10-tf256")
    columns = [vocabulary.index(label) for label in labels]
    tracks = {}
    with torch.inference_mode():
        for path in paths:
            features = np.load(path, allow_pickle=False).astype(np.float32)
            if features.shape != (250, 256) or not np.isfinite(features).all():
                raise ValueError(f"unexpected cached features: {path}")
            logits = torch.nn.functional.linear(torch.from_numpy(features), weight, bias)
            probs = torch.sigmoid(logits[:, columns]).numpy()
            tracks[ids[path.stem]] = (np.linspace(0.0, 10.0, 251).tolist(),
                                     {i: probs[:, i].tolist() for i in range(len(labels))})
    result = SEDMetrics.eval(refs, mode="frame", scores=tracks,
                             recordings={index: 10.0 for index in ids.values()}, threshold=0.5)
    independent_labels = []
    independent_scores = []
    for class_id in range(len(labels)):
        for recording_id, (boundaries, series) in tracks.items():
            class_refs = [(onset, offset) for rid, cid, onset, offset in refs
                          if rid == recording_id and cid == class_id]
            independent_labels.extend(
                any(onset < end and start < offset for onset, offset in class_refs)
                for start, end in zip(boundaries, boundaries[1:])
            )
            independent_scores.extend(series[class_id])
    comparison = {
        "f1": f1_score(independent_labels, np.asarray(independent_scores) >= 0.5),
        "average_precision": average_precision_score(independent_labels, independent_scores),
        "auroc": roc_auc_score(independent_labels, independent_scores),
    }
    for name, expected in comparison.items():
        if not np.isclose(result["micro"][name], expected, atol=1e-10, rtol=0):
            raise AssertionError(f"{name} mismatch: {result['micro'][name]} vs {expected}")
    print(json.dumps({
        "model": "EfficientSED fmn10-tf256 strong; pretrained head on cached encoder features",
        "checkpoint_sha256": checkpoint_hash,
        "versions": {"torch": torch.__version__, "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "split": "YOLiO pilot val derived from AudioSet Strong training shards; not held-out benchmark",
        "classes_selected_from": "most referenced classes in selected clips, for engineering smoke test only",
        "classes": labels, "recordings": len(paths), "threshold": 0.5,
        "score_grid": "250 intervals over 10 seconds; float16 cached features; no post-processing",
        "oracle": "micro F1, AP and AUROC match scikit-learn to 1e-10",
        "micro": result["micro"], "macro": result["macro"],
    }, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
