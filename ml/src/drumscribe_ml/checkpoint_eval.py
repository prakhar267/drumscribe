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
    split: str | None = None,
    fixed_checkpoint_thresholds: bool = False,
    family_competition: bool = False,
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
    if split is not None:
        records = [record for record in records if record.get("split") == split]
        if not records:
            raise TrainingError(f"evaluation dataset contains no {split!r} records")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = TrainingConfig(**state["configuration"])
    checkpoint_thresholds = dict(state.get("validationThresholds", {}))
    checkpoint_peak_distances = dict(state.get("validationPeakDistances", {}))
    if fixed_checkpoint_thresholds:
        missing_thresholds = [
            instrument.value
            for instrument in TRAINING_CLASSES
            if instrument.value not in checkpoint_thresholds
        ]
        if missing_thresholds:
            raise TrainingError(
                "checkpoint is missing fixed validation thresholds for: "
                + ", ".join(missing_thresholds)
            )
        missing_peak_distances = [
            instrument.value
            for instrument in TRAINING_CLASSES
            if instrument.value not in checkpoint_peak_distances
        ]
        if missing_peak_distances:
            raise TrainingError(
                "checkpoint is missing fixed validation peak distances for: "
                + ", ".join(missing_peak_distances)
            )
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
        thresholds=(checkpoint_thresholds if fixed_checkpoint_thresholds else None),
        peak_distances=(checkpoint_peak_distances if fixed_checkpoint_thresholds else None),
        family_competition=family_competition,
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
        "split": split,
        "thresholdSource": "checkpoint" if fixed_checkpoint_thresholds else "tuned_on_evaluation",
        "familyCompetition": family_competition,
        "peakDistances": metrics["peakDistances"],
        "supportedClassCount": len(per_class),
        "supportedMacroF1": float(metrics["macroF1"]),
        "strict14ClassMacroF1": sum(strict_scores) / len(strict_scores),
        "probeClasses": probe_classes,
        "probeMacroF1": sum(probe_scores) / len(probe_scores) if probe_scores else None,
        "perClassF1": per_class,
        "thresholds": metrics["thresholds"],
        "evidenceLevel": _evidence_level(
            evaluation_only=bool(payload.get("evaluationOnly")), split=split
        ),
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return destination


def _evidence_level(*, evaluation_only: bool, split: str | None) -> str:
    if evaluation_only:
        return "synthetic_reserved_validation_probe"
    if split == "test":
        return "natural_sealed_test"
    if split == "validation":
        return "natural_validation"
    if split == "train":
        return "natural_training_diagnostic"
    return "natural_mixed_split_evaluation"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
