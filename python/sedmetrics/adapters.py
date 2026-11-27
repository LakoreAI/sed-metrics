"""Adapters from on-disk dataset formats to :class:`sedmetrics.dataset.Dataset`.

Supported formats
-----------------
URBAN-SED v2.0.0
    ``annotations/<split>/<clip>.txt``, tab-separated ``onset<TAB>offset<TAB>
    label`` rows. Accepts an extracted directory or the official ``.tar.gz``.
AudioSet strong
    Parquet batches with an ``audio_len`` column and a ``raw_text`` column that
    carries a ``Strong events: (0.000s - 1.435s) Name (/m/xxxx) | ...`` line.

Loaders are strict: a row that cannot be parsed, or a missing duration, raises
instead of being skipped. Optional dependencies are imported only by the loader
that needs them (``pyarrow`` for AudioSet parquet).
"""

from __future__ import annotations

import math
import re
import tarfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from .dataset import Dataset

__all__ = [
    "load_audioset_strong",
    "load_urban_sed",
    "parse_audioset_strong_events",
    "parse_urban_sed_annotations",
]

_MAX_ANNOTATION_OVERRUN = 1.0
"""Largest tolerated overrun of an annotation past the nominal clip duration.

Both supported datasets round timestamps and then keep the original segment
timeline: URBAN-SED ends some events at ``10.000000000000002`` for a 10 s clip,
and AudioSet strong annotations can end up to ~0.43 s past the stored decoded
audio length. Anything more than a second past the duration is treated as a
corrupt row rather than a rounding artefact.
"""

_STRONG_EVENT_RE = re.compile(
    r"\(\s*(?P<onset>[0-9.]+)\s*s\s*-\s*(?P<offset>[0-9.]+)\s*s\s*\)"
    r"\s*(?P<name>.+?)\s*\((?P<mid>/[^()]+)\)\s*$"
)


# --- URBAN-SED ---------------------------------------------------------------


def _duration_including_annotations(
    duration: float, offsets: Iterable[float], context: str
) -> float:
    """Extend a nominal clip duration to the latest annotated offset."""
    for offset in offsets:
        if offset > duration + _MAX_ANNOTATION_OVERRUN:
            raise ValueError(
                f"{context}: an annotated event ends at {offset} s, more than "
                f"{_MAX_ANNOTATION_OVERRUN} s past the {duration} s clip; "
                "the annotation looks corrupt"
            )
        duration = max(duration, offset)
    return duration


def _is_metadata_file(name: str) -> bool:
    """macOS AppleDouble resource forks (``._name.txt``) are not annotations."""
    return name.startswith("._") or name == ".DS_Store"


def parse_urban_sed_annotations(
    text: str, source: str = "annotations"
) -> list[tuple[float, float, str]]:
    """Parse one URBAN-SED annotation file.

    Blank lines are ignored; anything else must be exactly
    ``onset<TAB>offset<TAB>label``. Returns ``(onset, offset, label)`` rows in
    file order.
    """
    events: list[tuple[float, float, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(
                f"{source}:{line_number}: expected 3 tab-separated fields "
                f"(onset, offset, label), got {len(fields)}: {line!r}"
            )
        onset_text, offset_text, label = (field.strip() for field in fields)
        try:
            onset = float(onset_text)
            offset = float(offset_text)
        except ValueError as error:
            raise ValueError(
                f"{source}:{line_number}: non-numeric timestamp in {line!r}"
            ) from error
        if not label:
            raise ValueError(f"{source}:{line_number}: empty event label")
        events.append((onset, offset, label))
    return events


def _urban_sed_annotations_root(root: Path) -> Path:
    if (root / "annotations").is_dir():
        return root / "annotations"
    candidate = root / "URBAN-SED_v2.0.0" / "annotations"
    if candidate.is_dir():
        return candidate
    raise ValueError(
        f"{root} does not look like an extracted URBAN-SED release: "
        "expected <root>/annotations or <root>/URBAN-SED_v2.0.0/annotations"
    )


def _iter_urban_sed_directory(
    annotations_root: Path, split: str
) -> Iterator[tuple[str, str, str]]:
    available = sorted(
        path.name for path in annotations_root.iterdir() if path.is_dir()
    )
    selected = available if split == "all" else [split]
    for split_name in selected:
        directory = annotations_root / split_name
        if not directory.is_dir():
            raise ValueError(
                f"URBAN-SED split {split_name!r} not found in {annotations_root}; "
                f"available splits: {available}"
            )
        for path in sorted(directory.glob("*.txt")):
            if _is_metadata_file(path.name):
                continue
            yield split_name, path.stem, path.read_text(encoding="utf-8")


def _iter_urban_sed_archive(
    archive_path: Path, split: str
) -> Iterator[tuple[str, str, str]]:
    """Read annotations from the official archive without extracting audio.

    The archive is read as a stream, so members are visited in stored order.
    Reading stops once the contiguous ``annotations/`` tree ends; URBAN-SED
    v2.0.0 stores annotations before audio. Extract the archive if a copy is
    ordered differently.
    """
    seen_annotations = False
    with tarfile.open(archive_path, mode="r|gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) == 4 and parts[1] == "annotations" and parts[3].endswith(
                ".txt"
            ):
                seen_annotations = True
                if split != "all" and parts[2] != split:
                    continue
                if _is_metadata_file(parts[3]):
                    continue
                file_object = archive.extractfile(member)
                if file_object is None:  # pragma: no cover - defensive
                    raise ValueError(f"cannot read {member.name} from {archive_path}")
                yield parts[2], Path(parts[3]).stem, file_object.read().decode("utf-8")
            elif seen_annotations and parts[1] != "annotations":
                break
    if not seen_annotations:
        raise ValueError(
            f"no annotations found in {archive_path}; the archive must follow the "
            "URBAN-SED v2.0.0 layout (annotations before audio), otherwise extract it first"
        )


def load_urban_sed(
    root: str | Path,
    *,
    split: str = "test",
    clip_duration: float = 10.0,
    limit: int | None = None,
) -> Dataset:
    """Load URBAN-SED annotations as a :class:`~sedmetrics.dataset.Dataset`.

    Parameters
    ----------
    root:
        Extracted release directory (containing ``annotations/``), or the
        official ``URBAN-SED_v2.0.0.tar.gz``.
    split:
        ``"train"``, ``"test"``, ``"validate"`` or ``"all"``.
    clip_duration:
        Duration assigned to every clip, in seconds. URBAN-SED v2.0.0 clips are
        10 s; the value is a documented convention because the loader reads
        annotations only, not the audio headers.
    limit:
        Stop after this many clips, for smoke tests. Class ids are then assigned
        from the loaded subset only.

    Notes
    -----
    Recording ids are assigned in sorted clip-name order. Clips without events
    are kept, so exposure and empty-recording behaviour stay visible.
    """
    if not math.isfinite(clip_duration) or clip_duration <= 0.0:
        raise ValueError(
            f"clip_duration must be finite and positive, got {clip_duration}"
        )
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    root = Path(root).expanduser()
    if not root.exists():
        raise FileNotFoundError(root)

    if root.is_file():
        annotations = list(_iter_urban_sed_archive(root, split))
        source_kind = f"{root.name} (split={split})"
    else:
        annotations = list(_iter_urban_sed_directory(_urban_sed_annotations_root(root), split))
        source_kind = f"{root} (split={split})"
    if not annotations:
        raise ValueError(f"no URBAN-SED annotations for split {split!r} in {root}")

    annotation_map: dict[str, list[tuple[float, float, str]]] = {}
    for split_name, clip_name, text in annotations:
        key = f"{split_name}/{clip_name}"
        if key in annotation_map:
            raise ValueError(f"duplicate URBAN-SED clip {key!r}")
        annotation_map[key] = parse_urban_sed_annotations(text, source=key)
        if limit is not None and len(annotation_map) >= limit:
            break

    class_labels = sorted(
        {label for rows in annotation_map.values() for _, _, label in rows}
    )
    class_ids = {label: index for index, label in enumerate(class_labels)}

    references: list[tuple[int, int, float, float]] = []
    durations: dict[int, float] = {}
    recording_names: dict[int, str] = {}
    used_clip_names: set[str] = set()
    for recording_id, key in enumerate(sorted(annotation_map)):
        rows = annotation_map[key]
        clip_name = key.split("/", 1)[1]
        if clip_name in used_clip_names:
            raise ValueError(f"clip name {clip_name!r} appears in several splits")
        used_clip_names.add(clip_name)
        recording_names[recording_id] = clip_name
        durations[recording_id] = _duration_including_annotations(
            clip_duration, (offset for _, offset, _ in rows), key
        )
        for onset, offset, label in rows:
            references.append((recording_id, class_ids[label], onset, offset))

    return Dataset(
        name="urban-sed",
        source=source_kind,
        references=tuple(references),
        durations=durations,
        class_names={class_id: label for label, class_id in class_ids.items()},
        recording_names=recording_names,
    )


# --- AudioSet strong ---------------------------------------------------------


def _strong_events_body(raw_text: Iterable[str] | str) -> str | None:
    lines = [raw_text] if isinstance(raw_text, str) else list(raw_text)
    strong = [line for line in lines if line.lstrip().startswith("Strong events:")]
    if not strong:
        return None
    if len(strong) > 1:
        raise ValueError("row has several 'Strong events:' lines")
    body = strong[0].partition(":")[2].strip()
    return body or None


def parse_audioset_strong_events(
    raw_text: Iterable[str] | str,
) -> list[tuple[float, float, str, str]]:
    """Parse the ``Strong events:`` line of an AudioSet strong row.

    Accepts the list of ``raw_text`` lines or the line itself. Returns
    ``(onset, offset, name, mid)`` rows, in stored order. A row without a
    ``Strong events:`` line is an empty clip.
    """
    body = _strong_events_body(raw_text)
    if body is None:
        return []
    events: list[tuple[float, float, str, str]] = []
    for chunk in body.split("|"):
        match = _STRONG_EVENT_RE.match(chunk.strip())
        if match is None:
            raise ValueError(f"unparsable AudioSet strong event {chunk.strip()!r}")
        events.append(
            (
                float(match.group("onset")),
                float(match.group("offset")),
                match.group("name"),
                match.group("mid"),
            )
        )
    return events


def _audioset_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = sorted(root.glob("*.parquet"))
    if not files:
        raise ValueError(f"no .parquet files in {root}")
    return files


def _import_parquet():
    try:
        import pyarrow.parquet as parquet
    except ModuleNotFoundError as error:  # pragma: no cover - depends on environment
        raise ImportError(
            "loading AudioSet strong parquet requires pyarrow; "
            "install it with `pip install sedmetrics[data]`"
        ) from error
    return parquet


def load_audioset_strong(
    root: str | Path,
    *,
    limit: int | None = None,
) -> Dataset:
    """Load AudioSet strong annotations from parquet batches.

    Parameters
    ----------
    root:
        A directory of ``*.parquet`` batches (for example
        ``data/raw/audioset_strong``), or a single parquet file.
    limit:
        Stop after this many recordings, for smoke tests. Class ids are then
        assigned from the loaded subset only.

    Notes
    -----
    Classes are identified by their AudioSet ontology id (``/m/...``), so two
    display names that collide across ids stay distinct. Recording ids follow
    file order and row order; names are ``"<file stem>#<row>"``.

    Durations come from the ``audio_len`` column, except that a recording whose
    annotated events end later than ``audio_len`` gets the latest annotated
    offset as its duration: the annotations live on the original segment
    timeline, and truncating them at the decoded audio length would silently
    discard labelled audio. In the sampled CLAPv2 batches this affects roughly
    10 % of rows, by up to 0.43 s.
    """
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    root = Path(root).expanduser()
    if not root.exists():
        raise FileNotFoundError(root)
    parquet = _import_parquet()

    rows: list[tuple[str, float, list[tuple[float, float, str, str]]]] = []
    for path in _audioset_files(root):
        table = parquet.read_table(path, columns=["raw_text", "audio_len"])
        for row_index, row in enumerate(table.to_pylist()):
            duration = float(row["audio_len"])
            if not math.isfinite(duration) or duration <= 0.0:
                raise ValueError(f"{path.name}#{row_index}: invalid duration {duration}")
            events = parse_audioset_strong_events(row["raw_text"])
            for onset, offset, name, mid in events:
                if not (math.isfinite(onset) and math.isfinite(offset)):
                    raise ValueError(
                        f"{path.name}#{row_index}: non-finite interval for {name!r}"
                    )
                if onset < 0.0 or offset <= onset:
                    raise ValueError(
                        f"{path.name}#{row_index}: event {name!r} "
                        f"[{onset}, {offset}) is not a positive interval"
                    )
                # Annotations live on the original segment timeline; keep them
                # by extending the duration instead of dropping labelled audio.
                duration = _duration_including_annotations(
                    duration, [offset], f"{path.name}#{row_index} ({name!r})"
                )
            rows.append((f"{path.stem}#{row_index}", duration, events))
            if limit is not None and len(rows) >= limit:
                break
        if limit is not None and len(rows) >= limit:
            break

    mid_names: dict[str, str] = {}
    for _, _, events in rows:
        for _, _, name, mid in events:
            mid_names.setdefault(mid, name)
    mid_ids = {mid: index for index, mid in enumerate(sorted(mid_names))}

    references: list[tuple[int, int, float, float]] = []
    durations: dict[int, float] = {}
    recording_names: dict[int, str] = {}
    for recording_id, (name, duration, events) in enumerate(rows):
        recording_names[recording_id] = name
        durations[recording_id] = duration
        for onset, offset, _, mid in events:
            references.append((recording_id, mid_ids[mid], onset, offset))

    return Dataset(
        name="audioset-strong",
        source=str(root),
        references=tuple(references),
        durations=durations,
        class_names={class_id: mid_names[mid] for mid, class_id in mid_ids.items()},
        recording_names=recording_names,
    )
