"""Dataset containers for evaluation.

A :class:`Dataset` holds reference events with stable integer identifiers for
recordings and classes, together with the metadata needed to interpret them
(recording durations, class vocabulary, human-readable names).

Loaders live in :mod:`sedmetrics.adapters`; this module has no optional
dependencies.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

EventTuple = tuple[int, int, float, float]
"""``(recording_id, class_id, onset, offset)`` in seconds."""

_FIELDS = ("recording_id", "class_id", "onset", "offset")


def _unpack(event: Any, index: int) -> tuple[Any, Any, float, float]:
    """Read an event given as a 4-item sequence, a mapping or an object."""
    if isinstance(event, Mapping):
        missing = [name for name in _FIELDS if name not in event]
        if missing:
            raise ValueError(f"event {index} is missing fields {missing}")
        return (
            event["recording_id"],
            event["class_id"],
            float(event["onset"]),
            float(event["offset"]),
        )
    if isinstance(event, Sequence) and not isinstance(event, (str, bytes)):
        if len(event) != 4:
            raise ValueError(
                f"event {index} has {len(event)} items; expected 4 "
                "(recording_id, class_id, onset, offset)"
            )
        return (event[0], event[1], float(event[2]), float(event[3]))
    try:
        return (
            getattr(event, "recording_id"),
            getattr(event, "class_id"),
            float(getattr(event, "onset")),
            float(getattr(event, "offset")),
        )
    except AttributeError as error:
        raise ValueError(
            f"event {index} is neither a 4-item sequence, a mapping with keys "
            f"{_FIELDS}, nor an object with those attributes"
        ) from error


@dataclass(frozen=True)
class Dataset:
    """Immutable reference dataset.

    Attributes
    ----------
    name:
        Short dataset name, for example ``"urban-sed"``.
    source:
        Where the data was read from, for reports and reproducibility.
    references:
        Reference events as ``(recording_id, class_id, onset, offset)``.
    durations:
        ``{recording_id: duration_seconds}``. Every recording present in the
        data must appear here, including recordings without events.
    class_names:
        ``{class_id: name}``; a stable, explicit vocabulary. Names need not be
        unique (AudioSet reuses display names across ontology ids); ambiguous
        names must be addressed by id.
    recording_names:
        ``{recording_id: name}`` for mapping system output back to files.
    """

    name: str
    source: str
    references: tuple[EventTuple, ...]
    durations: Mapping[int, float]
    class_names: Mapping[int, str]
    recording_names: Mapping[int, str]
    _class_ids: Mapping[str, int] = field(init=False, repr=False, compare=False)
    _ambiguous_class_names: frozenset[str] = field(
        init=False, repr=False, compare=False
    )
    _recording_ids: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        counts = Counter(self.class_names.values())
        ambiguous = frozenset(name for name, count in counts.items() if count > 1)
        class_ids = {
            name: class_id
            for class_id, name in self.class_names.items()
            if name not in ambiguous
        }
        recording_ids = {
            name: recording_id for recording_id, name in self.recording_names.items()
        }
        if len(recording_ids) != len(self.recording_names):
            raise ValueError("recording names are not unique")
        object.__setattr__(self, "durations", MappingProxyType(dict(self.durations)))
        object.__setattr__(self, "class_names", MappingProxyType(dict(self.class_names)))
        object.__setattr__(
            self, "recording_names", MappingProxyType(dict(self.recording_names))
        )
        object.__setattr__(self, "_class_ids", MappingProxyType(class_ids))
        object.__setattr__(self, "_ambiguous_class_names", ambiguous)
        object.__setattr__(self, "_recording_ids", MappingProxyType(recording_ids))

    @property
    def n_recordings(self) -> int:
        """Number of recordings, including those without events."""
        return len(self.durations)

    @property
    def n_classes(self) -> int:
        """Number of classes in the vocabulary."""
        return len(self.class_names)

    @property
    def n_events(self) -> int:
        """Number of reference events."""
        return len(self.references)

    def class_id(self, class_name_or_id: str | int) -> int:
        """Resolve a class name or id to an id.

        Raises for unknown ids and for names shared by several classes.
        """
        if isinstance(class_name_or_id, int):
            if class_name_or_id not in self.class_names:
                raise ValueError(f"unknown class id {class_name_or_id}")
            return class_name_or_id
        if class_name_or_id in self._ambiguous_class_names:
            raise ValueError(
                f"class name {class_name_or_id!r} is shared by several classes; "
                "address it by id"
            )
        try:
            return self._class_ids[class_name_or_id]
        except KeyError as error:
            raise ValueError(
                f"unknown class name {class_name_or_id!r}; "
                f"the dataset vocabulary has {self.n_classes} classes"
            ) from error

    def recording_id(self, recording_name_or_id: str | int) -> int:
        """Resolve a recording name or id to an id."""
        if isinstance(recording_name_or_id, int):
            if recording_name_or_id not in self.durations:
                raise ValueError(f"unknown recording id {recording_name_or_id}")
            return recording_name_or_id
        try:
            return self._recording_ids[recording_name_or_id]
        except KeyError as error:
            raise ValueError(
                f"unknown recording name {recording_name_or_id!r}"
            ) from error

    def encode(self, events: Iterable[Any]) -> list[EventTuple]:
        """Map names to ids, rejecting unknown recordings or classes.

        Nothing is dropped: an unknown name, a malformed event or a non-finite
        value raises instead of being skipped. Validation of intervals and
        recording boundaries happens in the metric itself.
        """
        encoded: list[EventTuple] = []
        for index, event in enumerate(events):
            recording, klass, onset, offset = _unpack(event, index)
            encoded.append(
                (
                    self.recording_id(recording),
                    self.class_id(klass),
                    onset,
                    offset,
                )
            )
        return encoded

    def psds(self, scores: Mapping[Any, Any], **kwargs: Any):
        """PSDS of per-frame ``scores`` against this dataset.

        ``scores`` maps a recording name or id to ``(boundaries, {class:
        per_frame_scores})`` where classes may be names or ids. See
        :func:`sedmetrics.psds.psds` for the keyword arguments.
        """
        from .psds import psds

        resolved: dict[int, tuple[Any, dict[int, Any]]] = {}
        for recording, payload in scores.items():
            boundaries, columns = payload
            resolved[self.recording_id(recording)] = (
                boundaries,
                {self.class_id(name): series for name, series in columns.items()},
            )
        return psds(
            self.references,
            resolved,
            recordings=self.durations,
            **kwargs,
        )

    def segment_f1(self, predictions: Iterable[Any], **kwargs: Any):
        """Segment-based metrics of ``predictions`` against this dataset.

        Predictions may use class and recording names or ids. See
        :func:`sedmetrics.segment.f1` for the keyword arguments.
        """
        from .segment import f1

        return f1(
            self.references,
            self.encode(predictions),
            recordings=self.durations,
            **kwargs,
        )

    def event_f1(self, predictions: Iterable[Any], **kwargs: Any):
        """Collar-based event F1 of ``predictions`` against this dataset.

        Predictions may use class and recording names or ids. See
        :func:`sedmetrics.event.f1` for the remaining keyword arguments.
        """
        from .event import f1

        return f1(
            self.references,
            self.encode(predictions),
            recordings=self.durations,
            **kwargs,
        )
