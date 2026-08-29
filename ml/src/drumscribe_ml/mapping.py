"""Dataset MIDI mapping into the complete canonical DrumScribe taxonomy."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from drumscribe_music import Instrument, canonical_instrument


@dataclass(frozen=True, slots=True)
class MappedMidiHit:
    instrument: Instrument
    onset_seconds: float
    velocity: int
    original_note: int


def map_midi_note(note: int) -> Instrument:
    return canonical_instrument(note)


def map_midi_hits(rows: Iterable[tuple[int, float, int]]) -> list[MappedMidiHit]:
    mapped = []
    for note, onset_seconds, velocity in rows:
        if onset_seconds < 0:
            raise ValueError("onset_seconds must be non-negative")
        if not 1 <= velocity <= 127:
            raise ValueError("velocity must be between 1 and 127")
        mapped.append(MappedMidiHit(map_midi_note(note), onset_seconds, velocity, note))
    return mapped
