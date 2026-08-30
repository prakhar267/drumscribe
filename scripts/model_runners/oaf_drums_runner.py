#!/usr/bin/env python3
"""Bridge the official Magenta Onsets-and-Frames Drums CLI to DrumScribe JSON."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from _midi_contract import write_contract

PROVIDER = "research-oaf-drums-v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument(
        "--executable", default="onsets_frames_transcription_transcribe"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="drumscribe-oaf-input-") as directory:
        copied = Path(directory) / "drums.wav"
        shutil.copyfile(args.input.resolve(), copied)
        argv = (
            args.executable,
            f"--model_dir={args.model_dir.resolve()}",
            "--config=drums",
            os.fspath(copied),
        )
        subprocess.run(argv, shell=False, check=True)
        midi = Path(os.fspath(copied) + ".midi")
        if not midi.is_file():
            raise RuntimeError("OaF completed without producing the expected MIDI file")
        write_contract(args.output.resolve(), provider=PROVIDER, midi_path=midi)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
