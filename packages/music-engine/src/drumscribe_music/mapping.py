"""Mappings between detector labels, canonical instruments, GM, and notation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Instrument

GM_PERCUSSION_CHANNEL = 9  # zero-based MIDI channel; conventionally displayed as channel 10

INSTRUMENT_TO_GM: dict[Instrument, int] = {
    Instrument.KICK: 36,
    Instrument.SNARE: 38,
    Instrument.CROSS_STICK: 37,
    Instrument.CLOSED_HIHAT: 42,
    Instrument.OPEN_HIHAT: 46,
    Instrument.PEDAL_HIHAT: 44,
    Instrument.RIDE: 51,
    Instrument.RIDE_BELL: 53,
    Instrument.CRASH: 49,
    Instrument.HIGH_TOM: 50,
    Instrument.MID_TOM: 47,
    Instrument.LOW_TOM: 45,
    Instrument.FLOOR_TOM: 41,
    Instrument.TAMBOURINE: 54,
}

GM_TO_INSTRUMENT: dict[int, Instrument] = {
    35: Instrument.KICK,
    36: Instrument.KICK,
    37: Instrument.CROSS_STICK,
    38: Instrument.SNARE,
    39: Instrument.SNARE,
    40: Instrument.SNARE,
    41: Instrument.FLOOR_TOM,
    43: Instrument.FLOOR_TOM,
    45: Instrument.LOW_TOM,
    47: Instrument.MID_TOM,
    48: Instrument.HIGH_TOM,
    50: Instrument.HIGH_TOM,
    42: Instrument.CLOSED_HIHAT,
    44: Instrument.PEDAL_HIHAT,
    46: Instrument.OPEN_HIHAT,
    49: Instrument.CRASH,
    52: Instrument.CRASH,
    55: Instrument.CRASH,
    57: Instrument.CRASH,
    51: Instrument.RIDE,
    59: Instrument.RIDE,
    53: Instrument.RIDE_BELL,
    54: Instrument.TAMBOURINE,
}


RAW_CLASS_ALIASES: dict[str, Instrument] = {
    "bd": Instrument.KICK,
    "bass_drum": Instrument.KICK,
    "bassdrum": Instrument.KICK,
    "kick": Instrument.KICK,
    "kick_drum": Instrument.KICK,
    "sd": Instrument.SNARE,
    "snare": Instrument.SNARE,
    "snare_drum": Instrument.SNARE,
    "rim": Instrument.CROSS_STICK,
    "rimshot": Instrument.CROSS_STICK,
    "cross_stick": Instrument.CROSS_STICK,
    "hihat": Instrument.CLOSED_HIHAT,
    "hi_hat": Instrument.CLOSED_HIHAT,
    "hh": Instrument.CLOSED_HIHAT,
    "closed_hihat": Instrument.CLOSED_HIHAT,
    "closed_hi_hat": Instrument.CLOSED_HIHAT,
    "open_hihat": Instrument.OPEN_HIHAT,
    "open_hi_hat": Instrument.OPEN_HIHAT,
    "ohh": Instrument.OPEN_HIHAT,
    "oh_h": Instrument.OPEN_HIHAT,
    "pedal_hihat": Instrument.PEDAL_HIHAT,
    "pedal_hi_hat": Instrument.PEDAL_HIHAT,
    "ride": Instrument.RIDE,
    "ride_cymbal": Instrument.RIDE,
    "ride_bell": Instrument.RIDE_BELL,
    "bell": Instrument.RIDE_BELL,
    "crash": Instrument.CRASH,
    "crash_cymbal": Instrument.CRASH,
    "cymbal": Instrument.CRASH,
    "high_tom": Instrument.HIGH_TOM,
    "hi_tom": Instrument.HIGH_TOM,
    "tom_high": Instrument.HIGH_TOM,
    "mid_tom": Instrument.MID_TOM,
    "tom_mid": Instrument.MID_TOM,
    "low_tom": Instrument.LOW_TOM,
    "tom_low": Instrument.LOW_TOM,
    "floor_tom": Instrument.FLOOR_TOM,
    "tambourine": Instrument.TAMBOURINE,
    "tmb": Instrument.TAMBOURINE,
}


@dataclass(frozen=True, slots=True)
class NotationPlacement:
    display_step: str
    display_octave: int
    notehead: str = "normal"
    stem: str = "up"


NOTATION_PLACEMENT: dict[Instrument, NotationPlacement] = {
    Instrument.KICK: NotationPlacement("F", 3, stem="down"),
    Instrument.FLOOR_TOM: NotationPlacement("A", 3, stem="down"),
    Instrument.LOW_TOM: NotationPlacement("C", 4, stem="down"),
    Instrument.SNARE: NotationPlacement("C", 5),
    Instrument.CROSS_STICK: NotationPlacement("C", 5, "x"),
    Instrument.MID_TOM: NotationPlacement("D", 5),
    Instrument.HIGH_TOM: NotationPlacement("E", 5),
    Instrument.CLOSED_HIHAT: NotationPlacement("G", 5, "x"),
    Instrument.OPEN_HIHAT: NotationPlacement("G", 5, "x"),
    Instrument.PEDAL_HIHAT: NotationPlacement("D", 4, "x", "down"),
    Instrument.RIDE: NotationPlacement("F", 5, "x"),
    Instrument.RIDE_BELL: NotationPlacement("F", 5, "diamond"),
    Instrument.CRASH: NotationPlacement("A", 5, "x"),
    Instrument.TAMBOURINE: NotationPlacement("E", 6, "x"),
}


def canonical_instrument(value: Instrument | str | int, *, strict: bool = True) -> Instrument:
    if isinstance(value, Instrument):
        return value
    if isinstance(value, int):
        try:
            return GM_TO_INSTRUMENT[value]
        except KeyError as exc:
            raise ValueError(f"unsupported GM percussion note: {value}") from exc
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if normalized.isdigit():
        return canonical_instrument(int(normalized), strict=strict)
    if normalized in RAW_CLASS_ALIASES:
        return RAW_CLASS_ALIASES[normalized]
    try:
        return Instrument[normalized.upper()]
    except KeyError as exc:
        if strict:
            raise ValueError(f"unknown drum instrument class: {value!r}") from exc
        return Instrument.SNARE


def gm_note(instrument: Instrument | str) -> int:
    return INSTRUMENT_TO_GM[canonical_instrument(instrument)]
