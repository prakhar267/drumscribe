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
    EXCLUSIVE_INSTRUMENT_FAMILIES,
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
StackedBlendStrategy = Literal["convex", "linear", "logit", "maximum", "noisy_or"]
EXCLUSIVE_FAMILIES_BY_NAME = {
    "HIHAT": EXCLUSIVE_INSTRUMENT_FAMILIES[0],
    "RIDE": EXCLUSIVE_INSTRUMENT_FAMILIES[1],
}


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


@dataclass(frozen=True, slots=True)
class StackedEnsembleRule:
    strategy: StackedBlendStrategy
    model_weights: dict[str, float]
    threshold: float
    peak_distance_frames: int
    temporal_kernel: tuple[float, ...] = (1.0,)
    temporal_blend: float = 0.0
    post_blend_model: str | None = None
    post_blend_strategy: Literal["convex", "logit"] | None = None
    post_blend_weight: float = 0.0

    def __post_init__(self) -> None:
        if self.strategy not in {"convex", "linear", "logit", "maximum", "noisy_or"}:
            raise TrainingError(f"unsupported stacked ensemble strategy: {self.strategy}")
        if not self.model_weights:
            raise TrainingError("stacked ensemble rules need at least one model")
        if any(not name.strip() for name in self.model_weights):
            raise TrainingError("stacked ensemble model names cannot be empty")
        if any(not math.isfinite(weight) for weight in self.model_weights.values()):
            raise TrainingError("stacked ensemble weights must be finite")
        if self.strategy in {"convex", "logit"} and not math.isclose(
            sum(self.model_weights.values()), 1.0, abs_tol=1e-6
        ):
            raise TrainingError(f"{self.strategy} ensemble weights must sum to one")
        if self.strategy == "convex" and any(weight < 0 for weight in self.model_weights.values()):
            raise TrainingError("convex ensemble weights cannot be negative")
        if self.strategy in {"maximum", "noisy_or"} and any(
            weight != 1 for weight in self.model_weights.values()
        ):
            raise TrainingError(f"{self.strategy} ensemble model weights must be one")
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise TrainingError("stacked ensemble threshold must be between zero and one")
        if self.peak_distance_frames < 1:
            raise TrainingError("stacked ensemble peak distance must be at least one frame")
        if (
            not self.temporal_kernel
            or len(self.temporal_kernel) % 2 == 0
            or any(not math.isfinite(value) or value < 0 for value in self.temporal_kernel)
            or sum(self.temporal_kernel) <= 0
        ):
            raise TrainingError("stacked ensemble temporal kernel must be positive and odd-length")
        if not math.isfinite(self.temporal_blend) or not 0 <= self.temporal_blend <= 1:
            raise TrainingError("stacked ensemble temporal blend must be between zero and one")
        post_blend_fields = (
            self.post_blend_model is not None,
            self.post_blend_strategy is not None,
            self.post_blend_weight != 0,
        )
        if any(post_blend_fields) and not all(post_blend_fields):
            raise TrainingError(
                "stacked ensemble post-blend model, strategy, and weight must be set together"
            )
        if self.post_blend_model is not None:
            if not self.post_blend_model.strip():
                raise TrainingError("stacked ensemble post-blend model cannot be empty")
            if self.post_blend_strategy not in {"convex", "logit"}:
                raise TrainingError("stacked ensemble post-blend strategy is invalid")
            if not math.isfinite(self.post_blend_weight) or not 0 < self.post_blend_weight <= 1:
                raise TrainingError("stacked ensemble post-blend weight must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class StackedEnsembleConfig:
    model_version: str
    models: dict[str, CheckpointReference]
    rules: dict[str, StackedEnsembleRule]
    onset_tolerance_frames: int = 2
    family_conflict_margins: dict[str, float] | None = None

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise TrainingError("stacked ensemble model version cannot be empty")
        if not self.models:
            raise TrainingError("stacked ensemble needs at least one checkpoint")
        expected = {instrument.value for instrument in TRAINING_CLASSES}
        actual = set(self.rules)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise TrainingError(
                f"stacked ensemble rules must cover every class; missing={missing}, extra={extra}"
            )
        unknown_models = sorted(
            {
                model
                for rule in self.rules.values()
                for model in rule.model_weights
                if model not in self.models
            }
            | {
                rule.post_blend_model
                for rule in self.rules.values()
                if rule.post_blend_model is not None and rule.post_blend_model not in self.models
            }
        )
        if unknown_models:
            raise TrainingError(
                f"stacked ensemble rules reference unknown models: {unknown_models}"
            )
        if self.onset_tolerance_frames < 0:
            raise TrainingError("stacked ensemble onset tolerance cannot be negative")
        if self.family_conflict_margins is not None:
            unknown_families = sorted(
                set(self.family_conflict_margins) - set(EXCLUSIVE_FAMILIES_BY_NAME)
            )
            if unknown_families:
                raise TrainingError(f"unknown exclusive family conflict rules: {unknown_families}")
            if any(
                not math.isfinite(margin) or margin < 0
                for margin in self.family_conflict_margins.values()
            ):
                raise TrainingError(
                    "exclusive family conflict margins must be finite and non-negative"
                )

    @classmethod
    def load(cls, path: Path) -> StackedEnsembleConfig:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("schemaVersion", 0)) != 2:
            raise TrainingError("stacked ensemble config requires schemaVersion 2")
        return cls(
            model_version=str(payload["modelVersion"]),
            models={
                name: _checkpoint_reference(value) for name, value in payload["models"].items()
            },
            onset_tolerance_frames=int(payload.get("onsetToleranceFrames", 2)),
            family_conflict_margins={
                str(name): float(margin)
                for name, margin in payload.get("familyConflictMargins", {}).items()
            }
            or None,
            rules={
                instrument: StackedEnsembleRule(
                    strategy=rule["strategy"],
                    model_weights={
                        name: float(weight) for name, weight in rule["modelWeights"].items()
                    },
                    threshold=float(rule["threshold"]),
                    peak_distance_frames=int(rule["peakDistanceFrames"]),
                    temporal_kernel=tuple(
                        float(value) for value in rule.get("temporalKernel", [1])
                    ),
                    temporal_blend=float(rule.get("temporalBlend", 0)),
                    post_blend_model=(
                        str(rule["postBlend"]["model"])
                        if rule.get("postBlend") is not None
                        else None
                    ),
                    post_blend_strategy=(
                        str(rule["postBlend"]["strategy"])
                        if rule.get("postBlend") is not None
                        else None
                    ),
                    post_blend_weight=(
                        float(rule["postBlend"]["weight"])
                        if rule.get("postBlend") is not None
                        else 0.0
                    ),
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


def blend_stacked_probabilities(
    model_probabilities: dict[str, np.ndarray],
    rules: dict[str, StackedEnsembleRule],
) -> np.ndarray:
    """Fuse named checkpoints and apply fixed temporal filters per drum class."""
    if not model_probabilities:
        raise TrainingError("stacked ensemble probabilities cannot be empty")
    shapes = {probabilities.shape for probabilities in model_probabilities.values()}
    if len(shapes) != 1:
        raise TrainingError("stacked ensemble probabilities must have the same shape")
    shape = next(iter(shapes))
    if len(shape) != 2 or shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("stacked ensemble probabilities must be frame-by-canonical-class")
    if any(
        not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or np.any(probabilities > 1)
        for probabilities in model_probabilities.values()
    ):
        raise TrainingError(
            "stacked ensemble probabilities must be finite and between zero and one"
        )

    output = np.empty(shape, dtype=np.float64)
    for index, instrument in enumerate(TRAINING_CLASSES):
        rule = rules[instrument.value]
        referenced_models = set(rule.model_weights)
        if rule.post_blend_model is not None:
            referenced_models.add(rule.post_blend_model)
        unknown = sorted(referenced_models - set(model_probabilities))
        if unknown:
            raise TrainingError(f"missing stacked ensemble probabilities for models: {unknown}")
        inputs = {name: model_probabilities[name][:, index] for name in rule.model_weights}
        if rule.strategy in {"convex", "linear"}:
            combined = sum(
                rule.model_weights[name] * probabilities for name, probabilities in inputs.items()
            )
            combined = np.clip(combined, 0, 1)
        elif rule.strategy == "logit":
            combined_logits = sum(
                rule.model_weights[name] * _probability_logit(probabilities)
                for name, probabilities in inputs.items()
            )
            combined = 1 / (1 + np.exp(-np.clip(combined_logits, -30, 30)))
        elif rule.strategy == "maximum":
            combined = np.maximum.reduce(list(inputs.values()))
        else:
            combined = 1 - np.prod(
                np.stack([1 - probabilities for probabilities in inputs.values()]), axis=0
            )
        if rule.temporal_blend:
            kernel = np.asarray(rule.temporal_kernel, dtype=np.float64)
            kernel /= kernel.sum()
            smoothed = _same_length_convolution(combined, kernel)
            combined = (1 - rule.temporal_blend) * combined + rule.temporal_blend * smoothed
        if rule.post_blend_model is not None:
            specialist = model_probabilities[rule.post_blend_model][:, index]
            if rule.post_blend_strategy == "convex":
                combined = (
                    1 - rule.post_blend_weight
                ) * combined + rule.post_blend_weight * specialist
            else:
                combined_logits = (1 - rule.post_blend_weight) * _probability_logit(
                    combined
                ) + rule.post_blend_weight * _probability_logit(specialist)
                combined = 1 / (1 + np.exp(-np.clip(combined_logits, -30, 30)))
        output[:, index] = combined
    return output


def decode_stacked_probabilities(
    probabilities: np.ndarray,
    rules: dict[str, StackedEnsembleRule],
    *,
    family_conflict_margins: dict[str, float] | None = None,
) -> dict[str, list[int]]:
    if probabilities.ndim != 2 or probabilities.shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("probabilities must be a frame-by-canonical-class matrix")
    decoded = {
        instrument.value: _peak_frames(
            probabilities[:, index],
            threshold=rules[instrument.value].threshold,
            minimum_distance_frames=rules[instrument.value].peak_distance_frames,
        )
        for index, instrument in enumerate(TRAINING_CLASSES)
    }
    if not family_conflict_margins:
        return decoded

    class_index = {instrument: index for index, instrument in enumerate(TRAINING_CLASSES)}
    unknown_families = sorted(set(family_conflict_margins) - set(EXCLUSIVE_FAMILIES_BY_NAME))
    if unknown_families:
        raise TrainingError(f"unknown exclusive family conflict rules: {unknown_families}")
    for family_name, minimum_margin in family_conflict_margins.items():
        if not math.isfinite(minimum_margin) or minimum_margin < 0:
            raise TrainingError("exclusive family conflict margins must be finite and non-negative")
        family = EXCLUSIVE_FAMILIES_BY_NAME[family_name]
        candidates_by_frame: dict[int, list[Any]] = {}
        for instrument in family:
            for frame in decoded[instrument.value]:
                candidates_by_frame.setdefault(frame, []).append(instrument)
        for frame, candidates in candidates_by_frame.items():
            if len(candidates) < 2:
                continue
            ranked = sorted(
                candidates,
                key=lambda instrument: (
                    float(
                        _probability_logit(probabilities[frame, class_index[instrument]])
                        - _probability_logit(np.asarray(rules[instrument.value].threshold))
                    ),
                    instrument.value,
                ),
                reverse=True,
            )
            winner = ranked[0]
            winner_margin = float(
                _probability_logit(probabilities[frame, class_index[winner]])
                - _probability_logit(np.asarray(rules[winner.value].threshold))
            )
            runner_up = ranked[1]
            runner_up_margin = float(
                _probability_logit(probabilities[frame, class_index[runner_up]])
                - _probability_logit(np.asarray(rules[runner_up.value].threshold))
            )
            if winner_margin - runner_up_margin < minimum_margin:
                continue
            for instrument in ranked[1:]:
                decoded[instrument.value].remove(frame)
    return decoded


def _probability_logit(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return np.log(clipped) - np.log1p(-clipped)


def _same_length_convolution(probabilities: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    radius = len(kernel) // 2
    padded = np.pad(probabilities, (radius, radius), mode="constant")
    return np.convolve(padded, kernel, mode="valid")


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


def evaluate_stacked_ensemble(
    config_path: Path,
    checkpoint_paths: dict[str, Path],
    prepared_dataset: Path,
    output_path: Path,
    *,
    device: str = "auto",
    split: str | None = None,
) -> Path:
    """Evaluate a frozen schema-v2 checkpoint stack without fitting evaluation labels."""
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires the training extra
        raise TrainingError("install the 'train' extra before evaluating ensembles") from exc

    config = StackedEnsembleConfig.load(config_path)
    expected_models = set(config.models)
    supplied_models = set(checkpoint_paths)
    if supplied_models != expected_models:
        missing = sorted(expected_models - supplied_models)
        extra = sorted(supplied_models - expected_models)
        raise TrainingError(
            f"stacked ensemble checkpoints must match config; missing={missing}, extra={extra}"
        )
    resolved_checkpoints = {name: Path(checkpoint_paths[name]).resolve() for name in config.models}
    for name, reference in config.models.items():
        _verify_checkpoint(resolved_checkpoints[name], reference)

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
    models = {}
    for name, checkpoint_path in resolved_checkpoints.items():
        state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        model_config = TrainingConfig(**state["configuration"])
        model = build_model(
            model_config,
            mel_bands=int(first_features.shape[1]),
            class_count=len(TRAINING_CLASSES),
        ).to(selected_device)
        model.load_state_dict(state["model"])
        model.eval()
        models[name] = model

    totals = {
        instrument.value: {"tp": 0, "fp": 0, "fn": 0, "support": 0}
        for instrument in TRAINING_CLASSES
    }
    with torch.no_grad():
        for record in records:
            features, targets, _ = _load_training_record(record)
            feature_tensor = torch.from_numpy(features)[None].to(selected_device)
            probabilities_by_model = {
                name: torch.sigmoid(model(feature_tensor)[0])[0].cpu().numpy()
                for name, model in models.items()
            }
            probabilities = blend_stacked_probabilities(probabilities_by_model, config.rules)
            predictions = decode_stacked_probabilities(
                probabilities,
                config.rules,
                family_conflict_margins=config.family_conflict_margins,
            )
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
    micro_tp = sum(counts["tp"] for counts in totals.values())
    micro_fp = sum(counts["fp"] for counts in totals.values())
    micro_fn = sum(counts["fn"] for counts in totals.values())
    micro_denominator = 2 * micro_tp + micro_fp + micro_fn
    report: dict[str, Any] = {
        "schemaVersion": 2,
        "modelVersion": config.model_version,
        "checkpointSha256": {name: config.models[name].sha256 for name in sorted(config.models)},
        "preparedDatasetSha256": _sha256(prepared),
        "recordCount": len(records),
        "split": split,
        "thresholdSource": "fixed_stacked_ensemble_config",
        "supportedClassCount": len(supported_scores),
        "supportedMacroF1": sum(supported_scores) / len(supported_scores),
        "strict14ClassMacroF1": sum(strict_scores) / len(strict_scores),
        "microF1": 2 * micro_tp / micro_denominator if micro_denominator else 0.0,
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
