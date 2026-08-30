"""Fixed, reproducible probability ensembling for drum-onset checkpoints."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .training import (
    TRAINING_CLASSES,
    TrainingConfig,
    TrainingError,
    _load_training_record,
    _match_frames,
    _peak_frames,
    _training_device,
    build_model,
)

BlendStrategy = Literal["convex", "maximum", "noisy_or"]


@dataclass(frozen=True, slots=True)
class EnsembleRule:
    strategy: BlendStrategy
    threshold: float
    peak_distance_frames: int
    secondary_weight: float = 0.0

    def __post_init__(self) -> None:
        if self.strategy not in {"convex", "maximum", "noisy_or"}:
            raise TrainingError(f"unsupported ensemble strategy: {self.strategy}")
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise TrainingError("ensemble threshold must be between zero and one")
        if self.peak_distance_frames < 1:
            raise TrainingError("ensemble peak distance must be at least one frame")
        if not math.isfinite(self.secondary_weight) or not 0 <= self.secondary_weight <= 1:
            raise TrainingError("ensemble secondary weight must be between zero and one")


@dataclass(frozen=True, slots=True)
class CheckpointReference:
    model_version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class EnsembleConfig:
    model_version: str
    primary: CheckpointReference
    secondary: CheckpointReference
    rules: dict[str, EnsembleRule]
    onset_tolerance_frames: int = 2

    def __post_init__(self) -> None:
        expected = {instrument.value for instrument in TRAINING_CLASSES}
        actual = set(self.rules)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise TrainingError(
                f"ensemble rules must cover every class; missing={missing}, extra={extra}"
            )
        if self.onset_tolerance_frames < 0:
            raise TrainingError("ensemble onset tolerance cannot be negative")

    @classmethod
    def load(cls, path: Path) -> EnsembleConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            model_version=str(payload["modelVersion"]),
            primary=_checkpoint_reference(payload["models"]["primary"]),
            secondary=_checkpoint_reference(payload["models"]["secondary"]),
            onset_tolerance_frames=int(payload.get("onsetToleranceFrames", 2)),
            rules={
                instrument: EnsembleRule(
                    strategy=rule["strategy"],
                    threshold=float(rule["threshold"]),
                    peak_distance_frames=int(rule["peakDistanceFrames"]),
                    secondary_weight=float(rule.get("secondaryWeight", 0)),
                )
                for instrument, rule in payload["rules"].items()
            },
        )


def blend_probabilities(
    primary: np.ndarray,
    secondary: np.ndarray,
    rules: dict[str, EnsembleRule],
) -> np.ndarray:
    """Blend two frame-aligned probability matrices using fixed per-class rules."""
    if primary.shape != secondary.shape or primary.ndim != 2:
        raise TrainingError("ensemble probabilities must be same-shape frame-by-class matrices")
    if primary.shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("ensemble probability class count does not match canonical classes")
    if not np.isfinite(primary).all() or not np.isfinite(secondary).all():
        raise TrainingError("ensemble probabilities must be finite")
    if np.any(primary < 0) or np.any(primary > 1) or np.any(secondary < 0) or np.any(secondary > 1):
        raise TrainingError("ensemble probabilities must be between zero and one")

    output = np.empty_like(primary, dtype=np.result_type(primary, secondary, np.float32))
    for index, instrument in enumerate(TRAINING_CLASSES):
        rule = rules[instrument.value]
        left = primary[:, index]
        right = secondary[:, index]
        if rule.strategy == "convex":
            output[:, index] = (1 - rule.secondary_weight) * left + rule.secondary_weight * right
        elif rule.strategy == "maximum":
            output[:, index] = np.maximum(left, right)
        else:
            output[:, index] = 1 - (1 - left) * (1 - right)
    return output


def decode_probabilities(
    probabilities: np.ndarray,
    rules: dict[str, EnsembleRule],
) -> dict[str, list[int]]:
    """Decode fixed per-class peaks without inspecting evaluation labels."""
    if probabilities.ndim != 2 or probabilities.shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("probabilities must be a frame-by-canonical-class matrix")
    return {
        instrument.value: _peak_frames(
            probabilities[:, index],
            threshold=rules[instrument.value].threshold,
            minimum_distance_frames=rules[instrument.value].peak_distance_frames,
        )
        for index, instrument in enumerate(TRAINING_CLASSES)
    }


def evaluate_ensemble(
    config_path: Path,
    primary_checkpoint_path: Path,
    secondary_checkpoint_path: Path,
    prepared_dataset: Path,
    output_path: Path,
    *,
    device: str = "auto",
    split: str | None = None,
) -> Path:
    """Evaluate a frozen ensemble; calibration is never fitted on evaluation labels."""
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires the training extra
        raise TrainingError("install the 'train' extra before evaluating ensembles") from exc

    config = EnsembleConfig.load(config_path)
    primary_path = Path(primary_checkpoint_path).resolve()
    secondary_path = Path(secondary_checkpoint_path).resolve()
    _verify_checkpoint(primary_path, config.primary)
    _verify_checkpoint(secondary_path, config.secondary)

    prepared = Path(prepared_dataset).resolve()
    payload = json.loads(prepared.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise TrainingError("evaluation dataset must contain records")
    if split is not None:
        records = [record for record in records if record.get("split") == split]
        if not records:
            raise TrainingError(f"evaluation dataset contains no {split!r} records")

    selected_device = _training_device(torch, device)
    first_features = np.load(records[0]["featurePath"])["features"]
    models = []
    for checkpoint_path in (primary_path, secondary_path):
        state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        model_config = TrainingConfig(**state["configuration"])
        model = build_model(
            model_config,
            mel_bands=int(first_features.shape[1]),
            class_count=len(TRAINING_CLASSES),
        ).to(selected_device)
        model.load_state_dict(state["model"])
        model.eval()
        models.append(model)

    totals = {
        instrument.value: {"tp": 0, "fp": 0, "fn": 0, "support": 0}
        for instrument in TRAINING_CLASSES
    }
    with torch.no_grad():
        for record in records:
            features, targets, _ = _load_training_record(record)
            feature_tensor = torch.from_numpy(features)[None].to(selected_device)
            model_probabilities = [
                torch.sigmoid(model(feature_tensor)[0])[0].cpu().numpy() for model in models
            ]
            probabilities = blend_probabilities(
                model_probabilities[0], model_probabilities[1], config.rules
            )
            predictions = decode_probabilities(probabilities, config.rules)
            for index, instrument in enumerate(TRAINING_CLASSES):
                references = np.flatnonzero(targets[:, index] > 0).tolist()
                tp, fp, fn = _match_frames(
                    references,
                    predictions[instrument.value],
                    tolerance=config.onset_tolerance_frames,
                )
                totals[instrument.value]["tp"] += tp
                totals[instrument.value]["fp"] += fp
                totals[instrument.value]["fn"] += fn
                totals[instrument.value]["support"] += len(references)

    per_class: dict[str, float] = {}
    for instrument in TRAINING_CLASSES:
        counts = totals[instrument.value]
        denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
        if counts["support"]:
            per_class[instrument.value] = 2 * counts["tp"] / denominator if denominator else 0.0
    supported_scores = list(per_class.values())
    strict_scores = [float(per_class.get(instrument.value, 0)) for instrument in TRAINING_CLASSES]
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "modelVersion": config.model_version,
        "primaryCheckpointSha256": config.primary.sha256,
        "secondaryCheckpointSha256": config.secondary.sha256,
        "preparedDatasetSha256": _sha256(prepared),
        "recordCount": len(records),
        "split": split,
        "thresholdSource": "fixed_ensemble_config",
        "supportedClassCount": len(supported_scores),
        "supportedMacroF1": sum(supported_scores) / len(supported_scores),
        "strict14ClassMacroF1": sum(strict_scores) / len(strict_scores),
        "perClassF1": per_class,
        "counts": totals,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return destination


def _checkpoint_reference(payload: dict[str, Any]) -> CheckpointReference:
    digest = str(payload["sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise TrainingError("checkpoint SHA-256 must be 64 lowercase hexadecimal characters")
    return CheckpointReference(model_version=str(payload["modelVersion"]), sha256=digest)


def _verify_checkpoint(path: Path, expected: CheckpointReference) -> None:
    actual = _sha256(path)
    if actual != expected.sha256:
        raise TrainingError(
            f"checkpoint hash mismatch for {expected.model_version}: "
            f"expected {expected.sha256}, got {actual}"
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
