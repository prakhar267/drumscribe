"""Reproducible validation/probe evaluation for self-hosted checkpoints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .training import (
    TRAINING_CLASSES,
    TrainingConfig,
    TrainingError,
    _training_device,
    _validation_metrics,
    build_model,
)


def evaluate_checkpoint(
    checkpoint_path: Path,
    prepared_dataset: Path,
    output_path: Path,
    *,
    device: str = "auto",
) -> Path:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires the training extra
        raise TrainingError("install the 'train' extra before evaluating checkpoints") from exc

    checkpoint = Path(checkpoint_path).resolve()
    prepared = Path(prepared_dataset).resolve()
    payload = json.loads(prepared.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise TrainingError("evaluation dataset must contain records")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = TrainingConfig(**state["configuration"])
    selected_device = _training_device(torch, device)
    first_features = np.load(records[0]["featurePath"])["features"]
    model = build_model(
        config,
        mel_bands=int(first_features.shape[1]),
        class_count=len(TRAINING_CLASSES),
    ).to(selected_device)
    model.load_state_dict(state["model"])
    metrics = _validation_metrics(
        model,
        records,
        tolerance_frames=config.onset_tolerance_frames,
        device=selected_device,
    )
    per_class = dict(metrics["perClassF1"])
    strict_scores = [float(per_class.get(instrument.value, 0.0)) for instrument in TRAINING_CLASSES]
    probe_classes = [
        str(value)
        for value in payload.get("oneShotProbe", {}).get("configuration", {}).get("classes", [])
    ]
    probe_scores = [float(per_class.get(value, 0.0)) for value in probe_classes]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "checkpoint": str(checkpoint),
        "checkpointSha256": _sha256(checkpoint),
        "preparedDataset": str(prepared),
        "preparedDatasetSha256": _sha256(prepared),
        "recordCount": len(records),
        "supportedClassCount": len(per_class),
        "supportedMacroF1": float(metrics["macroF1"]),
        "strict14ClassMacroF1": sum(strict_scores) / len(strict_scores),
        "probeClasses": probe_classes,
        "probeMacroF1": sum(probe_scores) / len(probe_scores) if probe_scores else None,
        "perClassF1": per_class,
        "thresholds": metrics["thresholds"],
        "evidenceLevel": "synthetic_reserved_validation_probe"
        if payload.get("evaluationOnly")
        else "natural_validation",
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
