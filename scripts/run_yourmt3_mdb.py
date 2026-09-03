#!/usr/bin/env python3
"""Run one loaded YourMT3+ checkpoint over an MDB research split."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

MODEL_RUNNERS_ROOT = Path(__file__).resolve().parent / "model_runners"
if os.fspath(MODEL_RUNNERS_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(MODEL_RUNNERS_ROOT))

from model_runners._midi_contract import write_contract
from model_runners.yourmt3_runner import DEFAULT_EXPERIMENT, DEFAULT_MODEL_ARGS

TRAIN_TRACKS = (
    "MusicDelta_80sRock",
    "MusicDelta_BebopJazz",
    "MusicDelta_Britpop",
    "MusicDelta_CoolJazz",
    "MusicDelta_Disco",
    "MusicDelta_FunkJazz",
    "MusicDelta_FusionJazz",
    "MusicDelta_Reggae",
    "MusicDelta_Rock",
    "MusicDelta_Rockabilly",
    "MusicDelta_Shadows",
    "MusicDelta_Zeppelin",
)
TEST_TRACKS = (
    "MusicDelta_Beatles",
    "MusicDelta_Country1",
    "MusicDelta_FreeJazz",
    "MusicDelta_Gospel",
    "MusicDelta_Grunge",
    "MusicDelta_Hendrix",
    "MusicDelta_LatinJazz",
    "MusicDelta_ModalJazz",
    "MusicDelta_Punk",
    "MusicDelta_SpeedMetal",
    "MusicDelta_SwingJazz",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-home", type=Path, required=True)
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/research-corpus/MDBDrums/MDB Drums"),
    )
    parser.add_argument("--audio-root", type=Path, default=Path("audio/drum_only"))
    parser.add_argument("--audio-suffix", default="_Drum.wav")
    parser.add_argument("--split", choices=("train", "test", "all"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    home = args.upstream_home.resolve(strict=True)
    dataset = args.dataset.resolve(strict=True)
    audio_root = args.audio_root
    if not audio_root.is_absolute():
        audio_root = dataset / audio_root
    audio_root = audio_root.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tracks = (
        TRAIN_TRACKS
        if args.split == "train"
        else TEST_TRACKS
        if args.split == "test"
        else TRAIN_TRACKS + TEST_TRACKS
    )

    sys.path.insert(0, os.fspath(home))
    sys.path.insert(0, os.fspath(home / "amt" / "src"))
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import model_helper
    import soundfile
    import torch

    def soundfile_load(uri):
        samples, sample_rate = soundfile.read(
            os.fspath(uri), dtype="float32", always_2d=True
        )
        return torch.from_numpy(samples.T.copy()), sample_rate

    model_helper.torchaudio.load = soundfile_load
    model_args = [args.experiment, *DEFAULT_MODEL_ARGS, "-pr", "32"]
    previous = Path.cwd()
    try:
        os.chdir(home)
        model = model_helper.load_model_checkpoint(args=model_args, device="cpu")
        model.to("cpu")
    finally:
        os.chdir(previous)

    with tempfile.TemporaryDirectory(prefix="drumscribe-yourmt3-mdb-") as directory:
        try:
            os.chdir(directory)
            for track in tracks:
                destination = output / f"{track}_yourmt3.json"
                if destination.exists():
                    print(f"Skipping existing {destination}", flush=True)
                    continue
                midi = Path(
                    model_helper.transcribe(
                        model,
                        {
                            "filepath": os.fspath(
                                audio_root / f"{track}{args.audio_suffix}"
                            ),
                            "track_name": track,
                        },
                    )
                ).resolve()
                write_contract(
                    destination,
                    provider="research-yourmt3-plus-v1",
                    midi_path=midi,
                )
                print(f"Transcribed {track}", flush=True)
        finally:
            os.chdir(previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
