#!/usr/bin/env python3
"""Bridge the separately licensed ADTOF PyTorch CLI to DrumScribe JSON."""

from __future__ import annotations

import argparse
import os
import statistics
import subprocess
import tempfile
from itertools import pairwise
from pathlib import Path

from _midi_contract import midi_hits, write_hits_contract

PROVIDER = "research-adtof-v1"
DECODER_VERSION = "rhythm-consistency-v1"
TOM_INSTRUMENTS = {"FLOOR_TOM", "LOW_TOM", "MID_TOM", "HIGH_TOM"}
HIHAT_INSTRUMENTS = {"CLOSED_HIHAT", "OPEN_HIHAT", "PEDAL_HIHAT"}
SNARE_INSTRUMENTS = {"SNARE", "CROSS_STICK"}


def _times(
    hits: list[dict[str, object]], instruments: set[str]
) -> list[float]:
    return sorted(
        float(hit["onsetSeconds"])
        for hit in hits
        if str(hit["instrument"]) in instruments
    )


def _near_any(onset: float, candidates: list[float], tolerance: float) -> bool:
    return any(abs(onset - candidate) <= tolerance for candidate in candidates)


def filter_rhythm_inconsistencies(
    hits: list[dict[str, object]],
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    """Remove two bounded ADTOF errors detectable from its own event sequence."""

    kicks = _times(hits, {"KICK"})
    hihats = _times(hits, HIHAT_INSTRUMENTS)
    snares = _times(hits, SNARE_INSTRUMENTS)
    toms = _times(hits, TOM_INSTRUMENTS)
    non_toms = sorted(
        float(hit["onsetSeconds"])
        for hit in hits
        if str(hit["instrument"]) not in TOM_INSTRUMENTS
    )

    kick_intervals = [right - left for left, right in pairwise(kicks)]
    median_kick_interval = statistics.median(kick_intervals) if kick_intervals else 0.0
    kick_hihat_collisions = sum(
        _near_any(kick, hihats, 0.04) for kick in kicks
    )
    slow_swing_pattern = (
        len(kicks) >= 8
        and 0.8 <= median_kick_interval <= 1.3
        and 1.5 * len(kicks) <= len(hihats) <= 2.5 * len(kicks)
        and kick_hihat_collisions / len(kicks) >= 0.7
        and len(snares) >= len(kicks)
    )

    tom_intervals = [right - left for left, right in pairwise(toms)]
    tom_interval_mean = statistics.fmean(tom_intervals) if tom_intervals else 0.0
    tom_interval_cv = (
        statistics.pstdev(tom_intervals) / tom_interval_mean
        if len(tom_intervals) >= 2 and tom_interval_mean > 0
        else float("inf")
    )
    pitched_intro_pattern = (
        len(toms) >= 6
        and bool(non_toms)
        and max(toms) < min(non_toms) - 0.5
        and tom_interval_cv < 0.25
    )

    adjustments: list[str] = []
    if pitched_intro_pattern:
        adjustments.append("suppress-regular-tom-only-intro")
    if slow_swing_pattern:
        adjustments.append("suppress-slow-swing-kick-hihat-collisions")

    filtered: list[dict[str, object]] = []
    for hit in hits:
        instrument = str(hit["instrument"])
        onset = float(hit["onsetSeconds"])
        if pitched_intro_pattern and instrument in TOM_INSTRUMENTS:
            continue
        if (
            slow_swing_pattern
            and instrument in HIHAT_INSTRUMENTS
            and _near_any(onset, kicks, 0.04)
        ):
            continue
        filtered.append(hit)
    return filtered, tuple(adjustments)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", default="adtof")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--thresholds", default="0.22,0.24,0.32,0.22,0.30")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="drumscribe-adtof-output-") as directory:
        midi = Path(directory) / "transcription.mid"
        argv = (
            args.executable,
            "--audio",
            os.fspath(args.input.resolve()),
            "--out",
            os.fspath(midi),
            "--thresholds",
            args.thresholds,
            "--fps",
            "100",
            "--device",
            args.device,
        )
        subprocess.run(argv, shell=False, check=True)
        if not midi.is_file():
            raise RuntimeError(
                "ADTOF completed without producing the expected MIDI file"
            )
        raw_hits = midi_hits(midi)
        filtered_hits, adjustments = filter_rhythm_inconsistencies(raw_hits)
        write_hits_contract(
            args.output.resolve(),
            provider=PROVIDER,
            hits=filtered_hits,
            metadata={
                "decoderVersion": DECODER_VERSION,
                "adjustments": list(adjustments),
                "removedHitCount": len(raw_hits) - len(filtered_hits),
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
