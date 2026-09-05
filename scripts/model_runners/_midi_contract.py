"""Shared MIDI-to-DrumScribe contract conversion for isolated model runners."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

GM_DRUM_CLASSES = {
    35: "KICK",
    36: "KICK",
    37: "CROSS_STICK",
    38: "SNARE",
    39: "SNARE",
    40: "SNARE",
    41: "FLOOR_TOM",
    42: "CLOSED_HIHAT",
    43: "FLOOR_TOM",
    44: "PEDAL_HIHAT",
    45: "LOW_TOM",
    46: "OPEN_HIHAT",
    47: "MID_TOM",
    48: "MID_TOM",
    49: "CRASH",
    50: "HIGH_TOM",
    51: "RIDE",
    52: "CRASH",
    53: "RIDE_BELL",
    54: "TAMBOURINE",
    55: "CRASH",
    57: "CRASH",
    59: "RIDE",
}


class MidiContractError(RuntimeError):
    pass


def midi_hits(path: Path, *, confidence: float = 0.5) -> list[dict[str, object]]:
    try:
        import mido
    except ImportError as exc:
        raise MidiContractError(
            "Install mido in the model runner environment."
        ) from exc
    midi = mido.MidiFile(os.fspath(path))
    elapsed = 0.0
    hits: list[dict[str, object]] = []
    for message in midi:
        elapsed += float(message.time)
        if message.type != "note_on" or int(message.velocity) <= 0:
            continue
        # Multi-instrument transcribers place drums on General MIDI channel 10
        # (zero-indexed channel 9). Filtering the channel is mandatory for direct
        # full-mix models: pitched instruments routinely use note numbers that
        # overlap GM percussion pitches.
        if int(getattr(message, "channel", -1)) != 9:
            continue
        instrument = GM_DRUM_CLASSES.get(int(message.note))
        if instrument is None:
            continue
        hits.append(
            {
                "instrument": instrument,
                "onsetSeconds": round(elapsed, 6),
                "velocity": max(1, min(127, int(message.velocity))),
                "confidence": confidence,
                "sourceMidiNote": int(message.note),
            }
        )
    hits.sort(key=lambda item: (float(item["onsetSeconds"]), str(item["instrument"])))
    return hits


def write_hits_contract(
    output: Path,
    *,
    provider: str,
    hits: Sequence[dict[str, object]],
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "schemaVersion": 1,
        "provider": provider,
        "hits": list(hits),
    }
    if metadata:
        payload["metadata"] = metadata
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(output)


def write_contract(output: Path, *, provider: str, midi_path: Path) -> None:
    write_hits_contract(output, provider=provider, hits=midi_hits(midi_path))
