#!/usr/bin/env python3
"""Run the frozen DrumScribe ensemble/OaF hybrid on an isolated drum stem."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from model_runners.drumscribe_oaf_runner import transcribe as transcribe_oaf
from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    FAMILY_SIX_MAP,
    load_models,
    predict_drumscribe,
)

PROVIDER = "drumscribe-hybrid-v1"
ENSEMBLE_FAMILIES = frozenset({"CYMBAL", "HIHAT"})


def _resolve(repository: Path, path: Path) -> Path:
    return (
        path.resolve(strict=True)
        if path.is_absolute()
        else (repository / path).resolve(strict=True)
    )


def transcribe(
    *,
    source: Path,
    repository: Path,
    ensemble_config: Path,
    oaf_checkpoint: Path,
    oaf_decoder: Path,
    device: str,
) -> dict[str, object]:
    import soundfile as sf
    import torch

    selected_device = device
    if selected_device == "auto":
        selected_device = (
            "cuda"
            if torch.cuda.is_available()
            else "mps"
            if torch.backends.mps.is_available()
            else "cpu"
        )
    configuration = StackedEnsembleConfig.load(ensemble_config)
    checkpoint_paths = {
        name: _resolve(repository, path) for name, path in CHECKPOINTS.items()
    }
    duration = sf.info(source).duration
    with tempfile.TemporaryDirectory(prefix="drumscribe-hybrid-") as directory:
        feature_path = Path(directory) / "features.npz"
        cache_log_mel(
            source,
            feature_path,
            PreparationConfig(seed="hybrid-inference", augmentation_variants=0),
        )
        with np.load(feature_path, allow_pickle=False) as arrays:
            mel_bands = int(arrays["features"].shape[1])
        models = load_models(
            configuration,
            checkpoint_paths,
            mel_bands,
            selected_device,
        )
        ensemble_rows = predict_drumscribe(
            feature_path,
            models,
            configuration,
            selected_device,
            duration,
        )

    oaf_payload = transcribe_oaf(
        oaf_checkpoint,
        source,
        selected_device,
        oaf_decoder,
    )
    hits = [
        {
            "instrument": instrument,
            "onsetSeconds": round(onset, 6),
            "velocity": 100,
            "confidence": 1.0,
            "sourceModel": configuration.model_version,
        }
        for onset, instrument in ensemble_rows
        if FAMILY_SIX_MAP.get(instrument) in ENSEMBLE_FAMILIES
    ]
    hits.extend(
        {**hit, "sourceModel": oaf_payload["modelVersion"]}
        for hit in oaf_payload["hits"]
        if FAMILY_SIX_MAP.get(str(hit["instrument"])) not in ENSEMBLE_FAMILIES
    )
    hits.sort(key=lambda item: (float(item["onsetSeconds"]), str(item["instrument"])))
    return {
        "schemaVersion": 1,
        "provider": PROVIDER,
        "modelVersion": (
            f"hybrid-{configuration.model_version}+{oaf_payload['modelVersion']}"
        ),
        "policy": {
            "ensembleFamilies": sorted(ENSEMBLE_FAMILIES),
            "oafFamilies": ["KICK", "SNARE", "TAMBOURINE", "TOM"],
        },
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument(
        "--ensemble-config",
        type=Path,
        default=Path("ml/configs/groove-stacked-articulation-v16.json"),
    )
    parser.add_argument("--oaf-checkpoint", type=Path, required=True)
    parser.add_argument("--oaf-decoder", type=Path, required=True)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    args = parser.parse_args()

    repository = args.repository.resolve(strict=True)
    payload = transcribe(
        source=args.input.resolve(strict=True),
        repository=repository,
        ensemble_config=_resolve(repository, args.ensemble_config),
        oaf_checkpoint=_resolve(repository, args.oaf_checkpoint),
        oaf_decoder=_resolve(repository, args.oaf_decoder),
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
