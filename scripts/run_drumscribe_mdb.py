#!/usr/bin/env python3
"""Run the frozen first-party DrumScribe ensemble across MDB audio files."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from run_competitive_drum_benchmark import CHECKPOINTS, load_models, predict_drumscribe

TRACKS = (
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


def _resolve(repository: Path, path: Path) -> Path:
    return (
        path.resolve(strict=True)
        if path.is_absolute()
        else (repository / path).resolve(strict=True)
    )


def _device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/research-corpus/MDBDrums/MDB Drums"),
    )
    parser.add_argument("--audio-root", type=Path, default=Path("audio/drum_only"))
    parser.add_argument("--audio-suffix", default="_Drum.wav")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("ml/configs/groove-stacked-articulation-v16.json"),
    )
    parser.add_argument("--feature-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    args = parser.parse_args()

    import soundfile as sf

    repository = args.repository.resolve(strict=True)
    dataset = _resolve(repository, args.dataset)
    audio_root = args.audio_root
    if not audio_root.is_absolute():
        audio_root = dataset / audio_root
    audio_root = audio_root.resolve(strict=True)
    feature_cache = args.feature_cache.resolve()
    output = args.output.resolve()
    feature_cache.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    configuration = StackedEnsembleConfig.load(_resolve(repository, args.config))
    checkpoint_paths = {
        name: _resolve(repository, path) for name, path in CHECKPOINTS.items()
    }
    preparation = PreparationConfig(
        seed="mdb-frozen-ensemble-inference", augmentation_variants=0
    )
    selected_device = _device(args.device)

    feature_paths: dict[str, Path] = {}
    for track in TRACKS:
        audio_path = audio_root / f"{track}{args.audio_suffix}"
        feature_path = feature_cache / f"{track}.npz"
        if not feature_path.exists():
            cache_log_mel(audio_path, feature_path, preparation)
        feature_paths[track] = feature_path
        print(json.dumps({"features": track}), flush=True)

    with np.load(feature_paths[TRACKS[0]], allow_pickle=False) as arrays:
        mel_bands = int(arrays["features"].shape[1])
    models = load_models(
        configuration,
        checkpoint_paths,
        mel_bands,
        selected_device,
    )

    for track in TRACKS:
        source = audio_root / f"{track}{args.audio_suffix}"
        destination = output / f"{track}_drumscribe.json"
        if destination.exists():
            print(json.dumps({"skipped": track, "reason": "output_exists"}), flush=True)
            continue
        hits = [
            {
                "instrument": instrument,
                "onsetSeconds": round(onset, 6),
                "velocity": 100,
                "confidence": 1.0,
            }
            for onset, instrument in predict_drumscribe(
                feature_paths[track],
                models,
                configuration,
                selected_device,
                sf.info(source).duration,
            )
        ]
        payload = {
            "schemaVersion": 1,
            "createdAt": datetime.now(UTC).isoformat(),
            "provider": "drumscribe-stacked-v16",
            "modelVersion": configuration.model_version,
            "hits": hits,
        }
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")))
        temporary.replace(destination)
        print(json.dumps({"predicted": track, "hits": len(hits)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
