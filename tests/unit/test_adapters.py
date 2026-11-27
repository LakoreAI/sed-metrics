"""Unit tests for the dataset container and the format adapters."""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

import sedmetrics as sm
from sedmetrics.adapters import (
    load_audioset_strong,
    load_urban_sed,
    parse_audioset_strong_events,
    parse_urban_sed_annotations,
)
from sedmetrics.dataset import Dataset

STRONG_LINE = (
    "Strong events: (0.000s - 1.435s) Male speech, man speaking (/m/05zppz) | "
    "(6.260s - 10.000s) Emergency vehicle (/m/03j1ly)"
)


def write_urban_sed(root: Path) -> Path:
    annotations = root / "annotations"
    (annotations / "test").mkdir(parents=True)
    (annotations / "train").mkdir()
    (annotations / "test" / "soundscape_test_1.txt").write_text(
        "1.0\t2.5\tsiren\n3.0\t4.0\tdog_bark\n", encoding="utf-8"
    )
    (annotations / "test" / "soundscape_test_2.txt").write_text("", encoding="utf-8")
    (annotations / "train" / "soundscape_train_1.txt").write_text(
        "0.0\t1.0\tsiren\n", encoding="utf-8"
    )
    # macOS resource forks ship next to the real files and are not annotations.
    (annotations / "test" / "._soundscape_test_1.txt").write_bytes(b"\x00\x05\x16\x07")
    (annotations / "test" / ".DS_Store").write_bytes(b"\x00\x00\x00\x01")
    return root


def test_parse_urban_sed_annotations_ignores_blank_lines() -> None:
    rows = parse_urban_sed_annotations("1.0\t2.0\tsiren\n\n2.5\t3.0\tdog_bark\n")
    assert rows == [(1.0, 2.0, "siren"), (2.5, 3.0, "dog_bark")]


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("1.0\tsiren\n", "3 tab-separated fields"),
        ("a\t2.0\tsiren\n", "non-numeric timestamp"),
        ("1.0\t2.0\t\n", "empty event label"),
    ],
)
def test_parse_urban_sed_annotations_rejects_malformed_rows(
    text: str, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        parse_urban_sed_annotations(text, source="clip.txt")


def test_parse_audioset_strong_events() -> None:
    rows = parse_audioset_strong_events([STRONG_LINE, "Tags: Speech"])
    assert rows == [
        (0.0, 1.435, "Male speech, man speaking", "/m/05zppz"),
        (6.26, 10.0, "Emergency vehicle", "/m/03j1ly"),
    ]


def test_parse_audioset_strong_events_accepts_the_line_itself() -> None:
    assert parse_audioset_strong_events(STRONG_LINE) == parse_audioset_strong_events(
        [STRONG_LINE]
    )


def test_rows_without_strong_events_are_empty_clips() -> None:
    assert parse_audioset_strong_events(["Tags: Speech"]) == []
    assert parse_audioset_strong_events(["Strong events:"]) == []


def test_parse_audioset_strong_events_rejects_malformed_chunks() -> None:
    with pytest.raises(ValueError, match="unparsable"):
        parse_audioset_strong_events(["Strong events: (0.0s - 1.0s) Wind"])

    with pytest.raises(ValueError, match="several 'Strong events:' lines"):
        parse_audioset_strong_events(["Strong events: ", "Strong events: "])


def test_load_urban_sed_from_directory(tmp_path: Path) -> None:
    dataset = load_urban_sed(write_urban_sed(tmp_path), split="test")

    assert dataset.name == "urban-sed"
    assert dataset.n_recordings == 2  # the empty annotation file is kept
    assert dataset.n_events == 2
    assert dataset.class_names == {0: "dog_bark", 1: "siren"}
    assert dataset.durations == {0: 10.0, 1: 10.0}
    assert dataset.recording_names == {
        0: "soundscape_test_1",
        1: "soundscape_test_2",
    }
    assert dataset.references == ((0, 1, 1.0, 2.5), (0, 0, 3.0, 4.0))


def test_load_urban_sed_from_official_archive_layout(tmp_path: Path) -> None:
    root = write_urban_sed(tmp_path / "extracted")
    archive_path = tmp_path / "URBAN-SED_v2.0.0.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(tmp_path / "extracted")
            archive.add(path, arcname=f"URBAN-SED_v2.0.0/{relative}")
        audio = tmp_path / "audio.wav"
        audio.write_bytes(b"not really audio")
        archive.add(audio, arcname="URBAN-SED_v2.0.0/audio/test/x.wav")

    from_archive = load_urban_sed(archive_path, split="test")
    from_directory = load_urban_sed(root, split="test")

    assert from_archive.references == from_directory.references
    assert from_archive.durations == from_directory.durations
    assert from_archive.class_names == from_directory.class_names


def test_load_urban_sed_limit_truncates_the_cohort(tmp_path: Path) -> None:
    dataset = load_urban_sed(write_urban_sed(tmp_path), split="test", limit=1)
    assert dataset.n_recordings == 1
    assert dataset.class_names == {0: "dog_bark", 1: "siren"}
    assert dataset.references == ((0, 1, 1.0, 2.5), (0, 0, 3.0, 4.0))


def test_load_urban_sed_rejects_unknown_split(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="available splits"):
        load_urban_sed(write_urban_sed(tmp_path), split="nope")


def test_load_audioset_strong(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")

    rows = [
        {"raw_text": [STRONG_LINE], "audio_len": 10.0},
        {"raw_text": ["Tags: Speech"], "audio_len": 5.0},
        {"raw_text": ["Strong events: (1.000s - 2.000s) Wind (/m/03m9d0z)"], "audio_len": 5.0},
    ]
    parquet.write_table(
        pyarrow.Table.from_pylist(rows), tmp_path / "train-batch0000.parquet"
    )

    dataset = load_audioset_strong(tmp_path)

    assert dataset.name == "audioset-strong"
    assert dataset.n_recordings == 3
    assert dataset.n_events == 3
    # Classes are identified by ontology id, not by display name.
    assert sorted(dataset.class_names.values()) == [
        "Emergency vehicle",
        "Male speech, man speaking",
        "Wind",
    ]
    assert dataset.durations == {0: 10.0, 1: 5.0, 2: 5.0}
    assert dataset.recording_names[2] == "train-batch0000#2"


def test_load_audioset_strong_keeps_annotations_past_the_decoded_audio(
    tmp_path: Path,
) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")

    rows = [
        {"raw_text": ["Strong events: (1.000s - 5.400s) Wind (/m/03m9d0z)"], "audio_len": 5.0}
    ]
    parquet.write_table(
        pyarrow.Table.from_pylist(rows), tmp_path / "train-batch0000.parquet"
    )

    dataset = load_audioset_strong(tmp_path)

    assert dataset.durations == {0: 5.4}


def test_load_audioset_strong_rejects_corrupt_offsets(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")

    rows = [
        {"raw_text": ["Strong events: (1.000s - 9.000s) Wind (/m/03m9d0z)"], "audio_len": 5.0}
    ]
    parquet.write_table(
        pyarrow.Table.from_pylist(rows), tmp_path / "train-batch0000.parquet"
    )

    with pytest.raises(ValueError, match="annotation looks corrupt"):
        load_audioset_strong(tmp_path)


def test_load_audioset_strong_limit(tmp_path: Path) -> None:
    pyarrow = pytest.importorskip("pyarrow")
    parquet = pytest.importorskip("pyarrow.parquet")

    rows = [{"raw_text": [STRONG_LINE], "audio_len": 10.0} for _ in range(3)]
    parquet.write_table(
        pyarrow.Table.from_pylist(rows), tmp_path / "train-batch0000.parquet"
    )

    assert load_audioset_strong(tmp_path, limit=2).n_recordings == 2


def make_dataset() -> Dataset:
    return Dataset(
        name="toy",
        source="unit test",
        references=((0, 10, 0.0, 1.0),),
        durations={0: 10.0},
        class_names={10: "siren", 11: "dog_bark"},
        recording_names={0: "clip_a"},
    )


def test_dataset_encodes_names_and_ids() -> None:
    dataset = make_dataset()
    encoded = dataset.encode(
        [
            ("clip_a", "siren", 0.0, 1.0),
            (0, 11, "2.0", "3.0"),
        ]
    )
    assert encoded == [(0, 10, 0.0, 1.0), (0, 11, 2.0, 3.0)]


def test_dataset_rejects_unknown_names_and_ids() -> None:
    dataset = make_dataset()
    with pytest.raises(ValueError, match="unknown class name"):
        dataset.encode([("clip_a", "explosion", 0.0, 1.0)])
    with pytest.raises(ValueError, match="unknown recording name"):
        dataset.encode([("clip_b", "siren", 0.0, 1.0)])
    with pytest.raises(ValueError, match="unknown class id"):
        dataset.class_id(99)
    with pytest.raises(ValueError, match="expected 4"):
        dataset.encode([("clip_a", "siren", 0.0)])


def test_ambiguous_class_names_must_be_addressed_by_id() -> None:
    dataset = Dataset(
        name="toy",
        source="unit test",
        references=(),
        durations={0: 1.0},
        class_names={0: "wind", 1: "wind"},
        recording_names={0: "clip"},
    )
    with pytest.raises(ValueError, match="shared by several classes"):
        dataset.class_id("wind")
    assert dataset.class_id(1) == 1


def test_dataset_event_f1_accepts_names(tmp_path: Path) -> None:
    dataset = load_urban_sed(write_urban_sed(tmp_path), split="test")
    result = dataset.event_f1([("soundscape_test_1", "siren", 1.05, 2.45)])

    assert result.n_correct == 1
    assert result.n_deletions == 1
    assert result.f1 == pytest.approx(2 / 3)
    assert result.config["onset_collar"] == 0.2


def test_dataset_is_read_only() -> None:
    dataset = make_dataset()
    with pytest.raises(TypeError):
        dataset.durations[1] = 5.0  # type: ignore[index]
    assert sm.Dataset is Dataset
