"""Dependency-free Standard MIDI File writer using GM percussion channel 10."""

from __future__ import annotations

import os
import struct
from collections.abc import Iterable
from fractions import Fraction
from pathlib import Path

from ..mapping import GM_PERCUSSION_CHANNEL, gm_note
from ..models import DrumEvent
from ..tempo import TempoMap

TICKS_PER_QUARTER = 480


def generate_midi(
    events: Iterable[DrumEvent], tempo_map: TempoMap, *, ticks_per_quarter: int = TICKS_PER_QUARTER
) -> bytes:
    if not 24 <= ticks_per_quarter <= 32_767:
        raise ValueError("ticks_per_quarter must be between 24 and 32767")
    conductor: list[tuple[int, int, bytes]] = []
    for change in tempo_map.changes:
        tick = _beat_tick(change.start_beat, ticks_per_quarter)
        micros = max(1, min(0xFFFFFF, round(60_000_000 / change.bpm)))
        conductor.append((tick, 0, b"\xff\x51\x03" + micros.to_bytes(3, "big")))
    for signature in tempo_map.time_signatures:
        tick = _beat_tick(signature.start_beat, ticks_per_quarter)
        denominator_power = signature.denominator.bit_length() - 1
        conductor.append(
            (
                tick,
                1,
                bytes((0xFF, 0x58, 0x04, signature.numerator, denominator_power, 24, 8)),
            )
        )
    conductor.append((0, 2, _text_meta(0x03, "DrumScribe conductor")))

    percussion: list[tuple[int, int, bytes]] = [(0, 0, _text_meta(0x03, "Drum set"))]
    for event in events:
        beat = (
            event.beat_position
            if event.beat_position is not None
            else tempo_map.seconds_to_beat(event.onset_seconds)
        )
        tick = max(0, _beat_tick(beat, ticks_per_quarter))
        if event.duration_seconds > 0:
            end_beat = tempo_map.seconds_to_beat(event.onset_seconds + event.duration_seconds)
            duration_ticks = max(
                1,
                _beat_tick(
                    end_beat - tempo_map.seconds_to_beat(event.onset_seconds), ticks_per_quarter
                ),
            )
        else:
            duration_ticks = max(1, ticks_per_quarter // 16)
        note = gm_note(event.instrument)
        percussion.append((tick, 2, bytes((0x90 | GM_PERCUSSION_CHANNEL, note, event.velocity))))
        percussion.append(
            (tick + duration_ticks, 1, bytes((0x80 | GM_PERCUSSION_CHANNEL, note, 0)))
        )

    header = b"MThd" + struct.pack(">IHHH", 6, 1, 2, ticks_per_quarter)
    return header + _track_chunk(conductor) + _track_chunk(percussion)


def write_midi(
    destination: str | os.PathLike[str],
    events: Iterable[DrumEvent],
    tempo_map: TempoMap,
    *,
    overwrite: bool = False,
) -> Path:
    return _write_bytes(destination, generate_midi(events, tempo_map), overwrite=overwrite)


def _track_chunk(items: list[tuple[int, int, bytes]]) -> bytes:
    body = bytearray()
    previous = 0
    for tick, _, payload in sorted(items, key=lambda item: (item[0], item[1], item[2])):
        if tick < previous:
            raise ValueError("MIDI events must be chronological")
        body.extend(_variable_length(tick - previous))
        body.extend(payload)
        previous = tick
    body.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(body)) + bytes(body)


def _beat_tick(beat: Fraction, resolution: int) -> int:
    scaled = beat * resolution
    quotient, remainder = divmod(scaled.numerator, scaled.denominator)
    return quotient + (1 if remainder * 2 >= scaled.denominator else 0)


def _variable_length(value: int) -> bytes:
    if value < 0 or value > 0x0FFFFFFF:
        raise ValueError("MIDI delta time out of range")
    buffer = value & 0x7F
    result = bytearray((buffer,))
    while value >> 7:
        value >>= 7
        buffer = (value & 0x7F) | 0x80
        result.insert(0, buffer)
    return bytes(result)


def _text_meta(kind: int, value: str) -> bytes:
    encoded = value.encode("utf-8")
    return bytes((0xFF, kind)) + _variable_length(len(encoded)) + encoded


def _write_bytes(destination: str | os.PathLike[str], payload: bytes, *, overwrite: bool) -> Path:
    path = Path(destination).expanduser().resolve(strict=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "wb" if overwrite else "xb"
    with path.open(mode) as handle:
        handle.write(payload)
    return path
