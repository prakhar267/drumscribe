#!/usr/bin/env python3
"""Run the frozen DrumScribe v19 development fusion on a mix and drum stem."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_ml.multiview import (
    MultiViewConfig,
    config_evidence,
    decode_multiview_probabilities,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingConfig, build_model

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    load_models,
    predict_stacked_probabilities,
)

PROVIDER = "drumscribe-multiview-v19-development"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _choose_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def specialist_probabilities(
    feature_path: Path,
    model: Any,
    *,
    device: str,
    limit: float,
) -> tuple[np.ndarray, float]:
    import torch

    with np.load(feature_path, allow_pickle=False) as arrays:
        features = arrays["features"].astype(np.float32)
        hop_length = int(arrays["hop_length"])
        sample_rate = int(arrays["sample_rate"])
    maximum_frames = min(features.shape[0], math.ceil(limit * sample_rate / hop_length))
    with torch.no_grad():
        logits, _ = model(torch.from_numpy(features[:maximum_frames])[None].to(device))
        probabilities = torch.sigmoid(logits)[0].cpu().numpy()
    return probabilities, hop_length / sample_rate


def transcribe(
    *,
    mixture: Path,
    stem: Path,
    repository: Path,
    multiview_config: Path,
    ensemble_config: Path,
    specialist_checkpoint: Path,
    device: str,
) -> dict[str, object]:
    import soundfile as sf
    import torch

    selected_device = _choose_device(device)
    mixture_duration = float(sf.info(mixture).duration)
    stem_duration = float(sf.info(stem).duration)
    if abs(mixture_duration - stem_duration) > 0.05:
        raise ValueError("mixture and drum stem durations must match within 50 ms")
    duration = min(mixture_duration, stem_duration)
    fusion = MultiViewConfig.load(multiview_config)
    evidence = config_evidence(multiview_config)
    components = evidence.get("components", {})
    expected_ensemble_hash = components.get("stackedEnsemble", {}).get("sha256")
    expected_specialist_hash = components.get("focalSpecialist", {}).get("sha256")
    if expected_ensemble_hash != _sha256(ensemble_config):
        raise RuntimeError(
            "stacked ensemble config hash does not match multi-view config"
        )
    if expected_specialist_hash != _sha256(specialist_checkpoint):
        raise RuntimeError(
            "specialist checkpoint hash does not match multi-view config"
        )
    configuration = StackedEnsembleConfig.load(ensemble_config)

    with tempfile.TemporaryDirectory(prefix="drumscribe-multiview-") as directory:
        feature_paths: dict[str, Path] = {}
        for name, source in (("mixture", mixture), ("stem", stem)):
            feature_path = Path(directory) / f"{name}.npz"
            cache_log_mel(
                source,
                feature_path,
                PreparationConfig(
                    seed="multiview-v19-inference", augmentation_variants=0
                ),
            )
            feature_paths[name] = feature_path
        with np.load(feature_paths["stem"], allow_pickle=False) as arrays:
            mel_bands = int(arrays["features"].shape[1])
        checkpoint_paths = {
            name: (repository / CHECKPOINTS[name]).resolve(strict=True)
            for name in configuration.models
        }
        ensemble_models = load_models(
            configuration, checkpoint_paths, mel_bands, selected_device
        )
        specialist_state = torch.load(
            specialist_checkpoint, map_location="cpu", weights_only=True
        )
        specialist_configuration = TrainingConfig(**specialist_state["configuration"])
        specialist = build_model(
            specialist_configuration,
            mel_bands=mel_bands,
            class_count=len(TRAINING_CLASSES),
        ).to(selected_device)
        specialist.load_state_dict(specialist_state["model"])
        specialist.eval()

        probability_sources: dict[str, np.ndarray] = {}
        frame_seconds: float | None = None
        for view in ("stem", "mixture"):
            ensemble, ensemble_frame_seconds = predict_stacked_probabilities(
                feature_paths[view],
                ensemble_models,
                configuration,
                selected_device,
                duration,
            )
            specialist_rows, specialist_frame_seconds = specialist_probabilities(
                feature_paths[view], specialist, device=selected_device, limit=duration
            )
            if not math.isclose(ensemble_frame_seconds, specialist_frame_seconds):
                raise RuntimeError("multi-view feature frame rates do not match")
            frame_seconds = ensemble_frame_seconds
            probability_sources[f"{view}Ensemble"] = ensemble
            probability_sources[f"{view}Specialist"] = specialist_rows

    assert frame_seconds is not None
    probabilities, decoded = decode_multiview_probabilities(
        probability_sources, fusion.rules
    )
    class_index = {
        instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)
    }
    hits = sorted(
        (
            {
                "instrument": instrument.value,
                "onsetSeconds": round(frame * frame_seconds, 6),
                "velocity": 100,
                "confidence": round(
                    float(probabilities[frame, class_index[instrument.value]]), 7
                ),
            }
            for instrument in TRAINING_CLASSES
            for frame in decoded[instrument.value]
            if frame * frame_seconds < duration
        ),
        key=lambda item: (float(item["onsetSeconds"]), str(item["instrument"])),
    )
    return {
        "schemaVersion": 1,
        "provider": PROVIDER,
        "modelVersion": fusion.model_version,
        "productionApproved": fusion.production_approved,
        "source": {
            "mixtureSha256": _sha256(mixture),
            "drumStemSha256": _sha256(stem),
        },
        "components": {
            "ensemble": configuration.model_version,
            "specialistCheckpointSha256": _sha256(specialist_checkpoint),
        },
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, help="original full mixture"
    )
    parser.add_argument(
        "--stem-input", type=Path, required=True, help="aligned drum stem"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--multiview-config",
        type=Path,
        default=Path("ml/configs/groove-multiview-articulation-v19.json"),
    )
    parser.add_argument(
        "--ensemble-config",
        type=Path,
        default=Path("ml/configs/groove-stacked-articulation-v18.json"),
    )
    parser.add_argument(
        "--specialist-checkpoint",
        type=Path,
        default=Path("ml/models/groove-egmd-focal-specialist-v18.pt"),
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    args = parser.parse_args()
    repository = args.repository.resolve(strict=True)

    def resolve(path: Path) -> Path:
        return (
            path.resolve(strict=True)
            if path.is_absolute()
            else (repository / path).resolve(strict=True)
        )

    payload = transcribe(
        mixture=resolve(args.input),
        stem=resolve(args.stem_input),
        repository=repository,
        multiview_config=resolve(args.multiview_config),
        ensemble_config=resolve(args.ensemble_config),
        specialist_checkpoint=resolve(args.specialist_checkpoint),
        device=args.device,
    )
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    temporary.replace(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
