"""Tests for the report builder, the predictions table reader and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import sedmetrics as sm
from sedmetrics import report


def make_dataset(tmp_path: Path) -> sm.Dataset:
    annotations = tmp_path / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "test" / "clip_a.txt").write_text(
        "1.0\t2.0\tsiren\n3.0\t4.0\tdog_bark\n", encoding="utf-8"
    )
    (annotations / "test" / "clip_b.txt").write_text("0.5\t1.5\tsiren\n", encoding="utf-8")
    return sm.adapters.load_urban_sed(tmp_path, split="test")


def test_evaluate_returns_a_json_safe_report(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path)
    result = report.evaluate(
        dataset,
        [
            ("clip_a", "siren", 1.05, 1.95),
            ("clip_a", "dog_bark", 3.0, 4.0),
            ("clip_b", "siren", 0.5, 1.5),
        ],
    )

    payload = json.dumps(result, allow_nan=False)
    loaded = json.loads(payload)

    assert loaded["sedmetrics_version"] == sm.__version__
    assert loaded["dataset"]["name"] == "urban-sed"
    assert loaded["dataset"]["n_recordings"] == 2
    assert loaded["predictions"]["n_events"] == 3
    assert set(loaded["metrics"]) == {"event_f1", "segment_f1"}
    assert loaded["metrics"]["event_f1"]["n_correct"] == 3
    assert loaded["metrics"]["segment_f1"]["f1"] == pytest.approx(1.0)
    assert loaded["metrics"]["event_f1"]["config"]["average"] == "micro"


def test_evaluate_forwards_metric_options(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path)
    result = report.evaluate(
        dataset,
        [("clip_a", "siren", 1.0, 2.0)],
        metrics=["event_f1"],
        event_f1_kwargs={"average": "macro", "onset_collar": 0.1},
    )

    assert result["metrics"]["event_f1"]["config"] == {
        "onset_collar": 0.1,
        "offset_collar": 0.2,
        "offset_ratio": 0.2,
        "evaluate_offset": True,
        "average": "macro",
    }


def test_unknown_metric_is_rejected(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path)
    with pytest.raises(ValueError, match="unknown metric"):
        report.evaluate(dataset, [], metrics=["psds"])


def test_unknown_class_in_predictions_is_rejected(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path)
    with pytest.raises(ValueError, match="unknown class name"):
        report.evaluate(dataset, [("clip_a", "explosion", 0.0, 1.0)])


def test_read_event_table_tsv_and_csv(tmp_path: Path) -> None:
    tsv = tmp_path / "predictions.tsv"
    tsv.write_text(
        "recording\tclass\tonset\toffset\n"
        "clip_a\tsiren\t1.05\t1.95\n"
        "\n"
        "clip_b\tsiren\t0.5\t1.5\n",
        encoding="utf-8",
    )
    assert report.read_event_table(tsv) == [
        ("clip_a", "siren", 1.05, 1.95),
        ("clip_b", "siren", 0.5, 1.5),
    ]

    csv = tmp_path / "predictions.csv"
    csv.write_text(
        "filename,event_label,event_onset,event_offset\nclip_a,siren,1.05,1.95\n",
        encoding="utf-8",
    )
    assert report.read_event_table(csv) == [("clip_a", "siren", 1.05, 1.95)]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("recording\tonset\toffset\nclip_a\t1.0\t2.0\n", "expected exactly one column"),
        ("recording\tclass\tonset\toffset\nclip_a\tsiren\tx\t2.0\n", "non-numeric"),
        ("recording\tclass\tonset\toffset\n\tsiren\t1.0\t2.0\n", "non-empty"),
    ],
)
def test_read_event_table_rejects_malformed_files(
    tmp_path: Path, text: str, match: str
) -> None:
    path = tmp_path / "predictions.tsv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        report.read_event_table(path)


def test_evaluate_file_and_write_report(tmp_path: Path) -> None:
    dataset = make_dataset(tmp_path)
    predictions = tmp_path / "predictions.tsv"
    predictions.write_text(
        "recording\tclass\tonset\toffset\nclip_a\tsiren\t1.05\t1.95\n",
        encoding="utf-8",
    )

    result = report.evaluate_file(dataset, predictions)
    assert result["metrics"]["event_f1"]["n_correct"] == 1

    out = report.write_report(result, tmp_path / "reports" / "run.json")
    assert json.loads(out.read_text(encoding="utf-8"))["predictions"]["n_events"] == 1


def test_cli_writes_a_report(tmp_path: Path) -> None:
    from sedmetrics.cli import main

    dataset_root = tmp_path / "dataset"
    annotations = dataset_root / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "test" / "clip_a.txt").write_text(
        "1.0\t2.0\tsiren\n", encoding="utf-8"
    )
    predictions = tmp_path / "predictions.tsv"
    predictions.write_text(
        "recording\tclass\tonset\toffset\nclip_a\tsiren\t1.0\t2.0\n", encoding="utf-8"
    )
    out = tmp_path / "report.json"

    exit_code = main(
        [
            "evaluate",
            "--dataset",
            "urban-sed",
            "--root",
            str(dataset_root),
            "--predictions",
            str(predictions),
            "--out",
            str(out),
        ]
    )

    assert exit_code == 0
    report_json = json.loads(out.read_text(encoding="utf-8"))
    assert report_json["metrics"]["event_f1"]["f1"] == 1.0
    assert report_json["metrics"]["segment_f1"]["f1"] == 1.0


def test_cli_prints_to_stdout(tmp_path: Path, capsys) -> None:
    from sedmetrics.cli import main

    dataset_root = tmp_path / "dataset"
    annotations = dataset_root / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "test" / "clip_a.txt").write_text("1.0\t2.0\tsiren\n", encoding="utf-8")
    predictions = tmp_path / "predictions.tsv"
    predictions.write_text(
        "recording\tclass\tonset\toffset\nclip_a\tsiren\t1.0\t2.0\n", encoding="utf-8"
    )

    assert main(["evaluate", "--dataset", "urban-sed", "--root", str(dataset_root),
                 "--predictions", str(predictions)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metrics"]["event_f1"]["n_correct"] == 1
