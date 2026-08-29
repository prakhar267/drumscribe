"""Piecewise tempo/time-signature conversion without cumulative rounding drift."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from math import isfinite


def as_fraction(value: int | float | str | Fraction) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("beat value must be finite")
        return Fraction(str(value)).limit_denominator(960_000)
    return Fraction(value)


@dataclass(frozen=True, slots=True, init=False)
class TempoChange:
    start_beat: Fraction
    bpm: float
    confidence: float = 1.0

    def __init__(
        self,
        start_beat: int | float | str | Fraction,
        bpm: float,
        confidence: float = 1.0,
    ) -> None:
        object.__setattr__(self, "start_beat", as_fraction(start_beat))
        object.__setattr__(self, "bpm", bpm)
        object.__setattr__(self, "confidence", confidence)
        if self.start_beat < 0:
            raise ValueError("tempo change start_beat must be non-negative")
        if not isfinite(self.bpm) or not 20 <= self.bpm <= 400:
            raise ValueError("bpm must be finite and between 20 and 400")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True, init=False)
class TimeSignature:
    numerator: int = 4
    denominator: int = 4
    start_beat: Fraction = Fraction(0)
    confidence: float = 1.0

    def __init__(
        self,
        numerator: int = 4,
        denominator: int = 4,
        start_beat: int | float | str | Fraction = Fraction(0),
        confidence: float = 1.0,
    ) -> None:
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "denominator", denominator)
        object.__setattr__(self, "start_beat", as_fraction(start_beat))
        object.__setattr__(self, "confidence", confidence)
        if self.start_beat < 0:
            raise ValueError("time signature start_beat must be non-negative")
        if not 1 <= self.numerator <= 32:
            raise ValueError("time signature numerator must be between 1 and 32")
        if (
            self.denominator < 1
            or self.denominator > 32
            or self.denominator & (self.denominator - 1)
        ):
            raise ValueError("time signature denominator must be a power of two up to 32")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    @property
    def quarter_note_beats_per_measure(self) -> Fraction:
        return Fraction(self.numerator * 4, self.denominator)


@dataclass(frozen=True, slots=True)
class MusicalPosition:
    measure_index: int
    beat_in_measure: Fraction
    absolute_beat: Fraction
    time_signature: TimeSignature


@dataclass(frozen=True, slots=True)
class TempoMap:
    changes: tuple[TempoChange, ...] = field(default_factory=lambda: (TempoChange(0, 120),))
    time_signatures: tuple[TimeSignature, ...] = field(default_factory=lambda: (TimeSignature(),))
    offset_seconds: float = 0.0

    def __post_init__(self) -> None:
        changes = tuple(sorted(self.changes, key=lambda change: change.start_beat))
        signatures = tuple(sorted(self.time_signatures, key=lambda signature: signature.start_beat))
        if not changes or changes[0].start_beat != 0:
            raise ValueError("tempo map must start with a tempo change at beat 0")
        if not signatures or signatures[0].start_beat != 0:
            raise ValueError("tempo map must start with a time signature at beat 0")
        if len({item.start_beat for item in changes}) != len(changes):
            raise ValueError("tempo changes must have unique start beats")
        if len({item.start_beat for item in signatures}) != len(signatures):
            raise ValueError("time signatures must have unique start beats")
        if not isfinite(self.offset_seconds) or self.offset_seconds < 0:
            raise ValueError("offset_seconds must be finite and non-negative")
        object.__setattr__(self, "changes", changes)
        object.__setattr__(self, "time_signatures", signatures)

    @classmethod
    def constant(
        cls,
        bpm: float = 120,
        numerator: int = 4,
        denominator: int = 4,
        *,
        offset_seconds: float = 0,
    ) -> TempoMap:
        return cls(
            (TempoChange(0, bpm),),
            (TimeSignature(numerator, denominator),),
            offset_seconds,
        )

    def tempo_at_beat(self, beat: int | float | str | Fraction) -> TempoChange:
        target = as_fraction(beat)
        current = self.changes[0]
        for change in self.changes[1:]:
            if change.start_beat > target:
                break
            current = change
        return current

    def beat_to_seconds(self, beat: int | float | str | Fraction) -> float:
        target = as_fraction(beat)
        if target < 0:
            return self.offset_seconds + float(target) * 60 / self.changes[0].bpm
        seconds = self.offset_seconds
        current_beat = Fraction(0)
        current_bpm = self.changes[0].bpm
        for change in self.changes[1:]:
            if change.start_beat >= target:
                break
            seconds += float(change.start_beat - current_beat) * 60 / current_bpm
            current_beat = change.start_beat
            current_bpm = change.bpm
        return seconds + float(target - current_beat) * 60 / current_bpm

    def seconds_to_beat(self, seconds: float) -> Fraction:
        if not isfinite(seconds):
            raise ValueError("seconds must be finite")
        relative = seconds - self.offset_seconds
        if relative < 0:
            return as_fraction(relative * self.changes[0].bpm / 60)
        elapsed = 0.0
        current_beat = Fraction(0)
        current_bpm = self.changes[0].bpm
        for change in self.changes[1:]:
            segment_seconds = float(change.start_beat - current_beat) * 60 / current_bpm
            if elapsed + segment_seconds >= relative:
                break
            elapsed += segment_seconds
            current_beat = change.start_beat
            current_bpm = change.bpm
        return current_beat + as_fraction((relative - elapsed) * current_bpm / 60)

    def signature_at_beat(self, beat: int | float | str | Fraction) -> TimeSignature:
        target = as_fraction(beat)
        current = self.time_signatures[0]
        for signature in self.time_signatures[1:]:
            if signature.start_beat > target:
                break
            current = signature
        return current

    def beat_to_position(self, beat: int | float | str | Fraction) -> MusicalPosition:
        target = as_fraction(beat)
        if target < 0:
            raise ValueError("notation positions cannot be before beat zero")
        measure_offset = 0
        current = self.time_signatures[0]
        segment_start = current.start_beat
        for signature in self.time_signatures[1:]:
            if signature.start_beat > target:
                break
            length = current.quarter_note_beats_per_measure
            measure_offset += _ceil_fraction((signature.start_beat - segment_start) / length)
            current = signature
            segment_start = signature.start_beat
        length = current.quarter_note_beats_per_measure
        within_segment = target - segment_start
        local_measure = int(within_segment // length)
        beat_in_measure = within_segment - local_measure * length
        return MusicalPosition(measure_offset + local_measure, beat_in_measure, target, current)

    def position_to_beat(
        self, measure_index: int, beat_in_measure: int | float | str | Fraction = 0
    ) -> Fraction:
        if measure_index < 0:
            raise ValueError("measure_index must be non-negative")
        remainder = measure_index
        for index, signature in enumerate(self.time_signatures):
            next_signature = (
                self.time_signatures[index + 1] if index + 1 < len(self.time_signatures) else None
            )
            length = signature.quarter_note_beats_per_measure
            if next_signature is None:
                return signature.start_beat + remainder * length + as_fraction(beat_in_measure)
            count = _ceil_fraction((next_signature.start_beat - signature.start_beat) / length)
            if remainder < count:
                return signature.start_beat + remainder * length + as_fraction(beat_in_measure)
            remainder -= count
        raise AssertionError("unreachable")

    def nearest_grid(
        self, seconds: float, subdivisions: Iterable[Fraction]
    ) -> tuple[Fraction, Fraction, float]:
        beat = self.seconds_to_beat(seconds)
        best: tuple[float, Fraction, Fraction, float] | None = None
        for step in subdivisions:
            step = as_fraction(step)
            if step <= 0:
                raise ValueError("grid subdivision must be positive")
            grid_beat = _round_fraction(beat / step) * step
            grid_seconds = self.beat_to_seconds(grid_beat)
            error = abs(grid_seconds - seconds)
            candidate = (error, -step, grid_beat, grid_seconds)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            raise ValueError("at least one subdivision is required")
        return best[2], -best[1], best[3]


def _round_fraction(value: Fraction) -> int:
    quotient, remainder = divmod(value.numerator, value.denominator)
    return quotient + (1 if remainder * 2 >= value.denominator else 0)


def _ceil_fraction(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)
