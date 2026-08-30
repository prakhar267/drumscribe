#!/usr/bin/env python3
"""Bridge the non-commercial ADTOF PyTorch CLI to DrumScribe JSON."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

from _midi_contract import write_contract

PROVIDER = "research-adtof-v1"


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
        write_contract(args.output.resolve(), provider=PROVIDER, midi_path=midi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
