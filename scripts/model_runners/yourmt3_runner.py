#!/usr/bin/env python3
"""Run the upstream YourMT3+ checkpoint and emit DrumScribe contract JSON.

The upstream checkout and weights are deliberately not vendored. Its licensing is
unresolved, so this runner is for local A/B research only.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from _midi_contract import write_contract

PROVIDER = "research-yourmt3-plus-v1"
DEFAULT_EXPERIMENT = (
    "mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops@last.ckpt"
)
DEFAULT_MODEL_ARGS = [
    "-p",
    "2024",
    "-tk",
    "mc13_full_plus_256",
    "-dec",
    "multi-t5",
    "-nl",
    "26",
    "-enc",
    "perceiver-tf",
    "-sqr",
    "1",
    "-ff",
    "moe",
    "-wf",
    "4",
    "-nmoe",
    "8",
    "-kmoe",
    "2",
    "-act",
    "silu",
    "-epe",
    "rope",
    "-rp",
    "1",
    "-ac",
    "spec",
    "-hop",
    "300",
    "-atc",
    "1",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-home", type=Path, required=True)
    parser.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    home = args.upstream_home.resolve()
    input_path = args.input.resolve()
    output_path = args.output.resolve()
    if not (home / "model_helper.py").is_file():
        raise SystemExit(f"YourMT3 model_helper.py not found under {home}")
    sys.path.insert(0, os.fspath(home))
    sys.path.insert(0, os.fspath(home / "amt" / "src"))
    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import model_helper
    import soundfile
    import torch

    def soundfile_load(uri):
        samples, sample_rate = soundfile.read(
            os.fspath(uri), dtype="float32", always_2d=True
        )
        return torch.from_numpy(samples.T.copy()), sample_rate

    # Torchaudio 2.11 made TorchCodec/shared-FFmpeg mandatory for load(). The
    # upstream model only needs a float tensor and sample rate, which SoundFile
    # supplies without changing inference semantics.
    model_helper.torchaudio.load = soundfile_load

    device = (
        "cuda" if args.device == "auto" and torch.cuda.is_available() else args.device
    )
    if device == "auto":
        device = "cpu"
    model_args = [
        args.experiment,
        *DEFAULT_MODEL_ARGS,
        "-pr",
        "16" if device == "cuda" else "32",
    ]
    previous = Path.cwd()
    try:
        os.chdir(home)
        model = model_helper.load_model_checkpoint(args=model_args, device="cpu")
        model.to(device)
    finally:
        os.chdir(previous)
    with tempfile.TemporaryDirectory(prefix="drumscribe-yourmt3-output-") as directory:
        try:
            os.chdir(directory)
            midi = Path(
                model_helper.transcribe(
                    model,
                    {"filepath": os.fspath(input_path), "track_name": "transcription"},
                )
            ).resolve()
            write_contract(output_path, provider=PROVIDER, midi_path=midi)
        finally:
            os.chdir(previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
