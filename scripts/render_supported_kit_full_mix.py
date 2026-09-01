#!/usr/bin/env python3
"""Add deterministic metal backing to a supported-kit drum test."""

from __future__ import annotations

import argparse
from pathlib import Path

import soundfile as sf
from build_supported_kit_corpus import _events
from run_sealed_metal_benchmark import _master
from run_supported_kit_benchmark import _backing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drums", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--song-index", type=int, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    drums, sample_rate = sf.read(args.drums.resolve(strict=True), always_2d=True)
    if sample_rate != 44_100:
        raise ValueError("supported-kit renderer expects 44.1 kHz drum audio")
    tempo, _ = _events(args.song_index)
    bpm = tempo.changes[0].bpm
    backing = _backing(
        tempo,
        len(drums) / sample_rate,
        bpm=bpm,
        bars=8,
    )
    full_mix = _master(0.82 * drums + 0.92 * backing[: len(drums)])
    sf.write(args.output, full_mix, sample_rate, subtype="PCM_24")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
