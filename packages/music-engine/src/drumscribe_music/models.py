"""Canonical, renderer-independent DrumScribe event models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from fractions import Fraction
from typing import Any
from uuid import uuid4


class Instrument(StrEnum):
    KICK = "KICK"
    SNARE = "SNARE"
    CROSS_STICK = "CROSS_STICK"
    CLOSED_HIHAT = "CLOSED_HIHAT"
    OPEN_HIHAT = "OPEN_HIHAT"
    PEDAL_HIHAT = "PEDAL_HIHAT"
    RIDE = "RIDE"
    RIDE_BELL = "RIDE_BELL"
    CRASH = "CRASH"
    HIGH_TOM = "HIGH_TOM"
    MID_TOM = "MID_TOM"
    LOW_TOM = "LOW_TOM"
    FLOOR_TOM = "FLOOR_TOM"
    TAMBOURINE = "TAMBOURINE"


class EventSource(StrEnum):
    TRANSCRIPTION = "TRANSCRIPTION"
    MANUAL = "MANUAL"
    IMPORTED_MIDI = "IMPORTED_MIDI"
    SYNTHETIC = "SYNTHETIC"


class GridSubdivision(StrEnum):
    QUARTER = "quarter"
    EIGHTH = "eighth"
    SIXTEENTH = "sixteenth"
    THIRTY_SECOND = "thirty_second"
    EIGHTH_TRIPLET = "eighth_triplet"
    SIXTEENTH_TRIPLET = "sixteenth_triplet"

    @property
    def beats(self) -> Fraction:
        return {
            GridSubdivision.QUARTER: Fraction(1),
            GridSubdivision.EIGHTH: Fraction(1, 2),
            GridSubdivision.SIXTEENTH: Fraction(1, 4),
            GridSubdivision.THIRTY_SECOND: Fraction(1, 8),
            GridSubdivision.EIGHTH_TRIPLET: Fraction(1, 3),
            GridSubdivision.SIXTEENTH_TRIPLET: Fraction(1, 6),
        }[self]


def _finite_nonnegative(value: float, name: str) -> None:
    if value < 0 or value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class RawDrumHit:
    """A timed detector result before any musical-grid decisions."""

    instrument_class: Instrument | str
    onset_seconds: float
    velocity: int = 100
    confidence: float = 1.0
    duration_seconds: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _finite_nonnegative(self.onset_seconds, "onset_seconds")
        _finite_nonnegative(self.duration_seconds, "duration_seconds")
        if not 1 <= self.velocity <= 127:
            raise ValueError("velocity must be between 1 and 127")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(self.instrument_class, (str, Instrument)):
            raise TypeError("instrument_class must be a string or Instrument")


@dataclass(frozen=True, slots=True)
class DrumEvent:
    """Canonical editable event; raw timing is never overwritten by quantization."""

    instrument: Instrument
    onset_seconds: float
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str | None = None
    duration_seconds: float = 0.0
    velocity: int = 100
    confidence: float = 1.0
    source: EventSource = EventSource.TRANSCRIPTION
    beat_position: Fraction | None = None
    measure_index: int | None = None
    beat_in_measure: Fraction | None = None
    subdivision: GridSubdivision | None = None
    quantized_onset_seconds: float | None = None
    manually_edited: bool = False
    is_grace: bool = False
    grace_of_event_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not isinstance(self.instrument, Instrument):
            object.__setattr__(self, "instrument", Instrument(self.instrument))
        if not isinstance(self.source, EventSource):
            object.__setattr__(self, "source", EventSource(self.source))
        if self.subdivision is not None and not isinstance(self.subdivision, GridSubdivision):
            object.__setattr__(self, "subdivision", GridSubdivision(self.subdivision))
        if self.beat_position is not None and not isinstance(self.beat_position, Fraction):
            object.__setattr__(self, "beat_position", _coerce_fraction(self.beat_position))
        if self.beat_in_measure is not None and not isinstance(self.beat_in_measure, Fraction):
            object.__setattr__(self, "beat_in_measure", _coerce_fraction(self.beat_in_measure))
        _finite_nonnegative(self.onset_seconds, "onset_seconds")
        _finite_nonnegative(self.duration_seconds, "duration_seconds")
        if self.quantized_onset_seconds is not None:
            _finite_nonnegative(self.quantized_onset_seconds, "quantized_onset_seconds")
        if not 1 <= self.velocity <= 127:
            raise ValueError("velocity must be between 1 and 127")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.measure_index is not None and self.measure_index < 0:
            raise ValueError("measure_index must be non-negative")
        if self.beat_position is not None and self.beat_position < 0:
            raise ValueError("beat_position must be non-negative")
        if self.beat_in_measure is not None and self.beat_in_measure < 0:
            raise ValueError("beat_in_measure must be non-negative")
        if self.grace_of_event_id == self.id:
            raise ValueError("a grace event cannot reference itself")

    @property
    def playback_onset_seconds(self) -> float:
        """Original-performance timing used by synchronized playback."""

        return self.onset_seconds

    @property
    def notation_onset_seconds(self) -> float:
        """Readable timing used by notation/export projections."""

        return (
            self.quantized_onset_seconds
            if self.quantized_onset_seconds is not None
            else self.onset_seconds
        )

    def edited(self, **changes: Any) -> DrumEvent:
        changes.setdefault("manually_edited", True)
        changes.setdefault("updated_at", datetime.now(UTC))
        return replace(self, **changes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "projectId": self.project_id,
            "instrument": self.instrument.value,
            "onsetSeconds": self.onset_seconds,
            "durationSeconds": self.duration_seconds,
            "velocity": self.velocity,
            "confidence": self.confidence,
            "source": self.source.value,
            "beatPosition": _fraction_json(self.beat_position),
            "measureIndex": self.measure_index,
            "beatInMeasure": _fraction_json(self.beat_in_measure),
            "subdivision": self.subdivision.value if self.subdivision else None,
            "quantizedOnset": self.quantized_onset_seconds,
            "manuallyEdited": self.manually_edited,
            "isGrace": self.is_grace,
            "graceOfEventId": self.grace_of_event_id,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
        }


def _fraction_json(value: Fraction | None) -> str | None:
    if value is None:
        return None
    return (
        str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
    )


def _coerce_fraction(value: Any) -> Fraction:
    if isinstance(value, float):
        return Fraction(str(value)).limit_denominator(960_000)
    return Fraction(value)
