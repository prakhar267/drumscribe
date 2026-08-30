"""Configuration-driven, resumable self-hosted drum onset training path."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import uuid
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
from drumscribe_music import Instrument


class TrainingError(RuntimeError):
    pass


TRAINING_CLASSES = tuple(Instrument)


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    prepared_dataset: str
    output_root: str
    model_version: str
    epochs: int = 80
    early_stopping_patience: int = 10
    learning_rate: float = 0.0003
    hidden_size: int = 192
    dropout: float = 0.2
    onset_tolerance_frames: int = 2
    window_frames: int = 2_048
    batch_size: int = 8
    seed: int = 20260829
    resume_checkpoint: str | None = None
    resume_learning_rate: float | None = None
    device: str = "auto"
    architecture: Literal["crnn", "spectral_moe"] = "crnn"
    moe_experts: int = 8
    moe_top_k: int = 2
    lr_decay_patience: int = 2
    lr_decay_factor: float = 0.5
    minimum_learning_rate: float = 0.000001

    def __post_init__(self) -> None:
        if not self.model_version.strip() or "/" in self.model_version:
            raise TrainingError("model_version must be a non-empty filesystem-safe version")
        if self.epochs < 1 or self.early_stopping_patience < 1 or self.hidden_size < 16:
            raise TrainingError("epochs, patience, and hidden size must be positive")
        if self.onset_tolerance_frames < 0 or self.window_frames < 64 or self.batch_size < 1:
            raise TrainingError("onset tolerance and training window are invalid")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise TrainingError("learning_rate must be positive and finite")
        if self.resume_learning_rate is not None and (
            not math.isfinite(self.resume_learning_rate)
            or not self.minimum_learning_rate <= self.resume_learning_rate <= self.learning_rate
        ):
            raise TrainingError(
                "resume_learning_rate must be finite and between minimum_learning_rate "
                "and learning_rate"
            )
        if not 0 <= self.dropout < 1:
            raise TrainingError("dropout must be between zero and one")
        if self.device not in {"auto", "cpu", "cuda", "mps"}:
            raise TrainingError("device must be auto, cpu, cuda, or mps")
        if self.architecture not in {"crnn", "spectral_moe"}:
            raise TrainingError("architecture must be crnn or spectral_moe")
        if self.moe_experts < 2 or not 1 <= self.moe_top_k <= self.moe_experts:
            raise TrainingError("MoE expert count or top-k routing is invalid")
        if self.lr_decay_patience < 1 or not 0 < self.lr_decay_factor < 1:
            raise TrainingError("learning-rate decay patience/factor are invalid")
        if not 0 < self.minimum_learning_rate <= self.learning_rate:
            raise TrainingError("minimum learning rate must be positive and at most learning_rate")

    @classmethod
    def load(cls, path: Path) -> TrainingConfig:
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def build_model(config: TrainingConfig, *, mel_bands: int, class_count: int):
    try:
        import torch
        import torch.nn as nn
    except ImportError as exc:  # pragma: no cover - exercised only with training extra
        raise TrainingError("install the 'train' extra to build the self-hosted model") from exc

    class DrumOnsetNetwork(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv1d(mel_bands, 128, kernel_size=5, padding=2),
                nn.BatchNorm1d(128),
                nn.GELU(),
                nn.Dropout(config.dropout),
                nn.Conv1d(128, 160, kernel_size=5, padding=4, dilation=2),
                nn.GELU(),
            )
            self.temporal = nn.GRU(
                160,
                config.hidden_size,
                batch_first=True,
                bidirectional=True,
            )
            self.onset_head = nn.Linear(config.hidden_size * 2, class_count)
            self.velocity_head = nn.Sequential(
                nn.Linear(config.hidden_size * 2, class_count), nn.Sigmoid()
            )

        def forward(self, features):
            encoded = self.encoder(features.transpose(1, 2)).transpose(1, 2)
            contextual, _ = self.temporal(encoded)
            return self.onset_head(contextual), self.velocity_head(contextual)

    class SpectralMoEDrumOnsetNetwork(nn.Module):
        """Frame-aligned spectral BiGRU with sparse expert routing.

        This is a clean-room DrumScribe architecture. It borrows only the general
        Mixture-of-Experts design idea from the research comparison, not upstream
        source code or weights.
        """

        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv1d(mel_bands, 128, kernel_size=5, padding=2),
                nn.BatchNorm1d(128),
                nn.SiLU(),
                nn.Conv1d(128, 160, kernel_size=5, padding=4, dilation=2),
                nn.SiLU(),
                nn.Dropout(config.dropout),
            )
            self.temporal = nn.GRU(
                160,
                config.hidden_size,
                batch_first=True,
                bidirectional=True,
            )
            width = config.hidden_size * 2
            self.router = nn.Linear(width, config.moe_experts)
            self.experts = nn.ModuleList(
                nn.Sequential(
                    nn.Linear(width, width * 2),
                    nn.SiLU(),
                    nn.Dropout(config.dropout),
                    nn.Linear(width * 2, width),
                )
                for _ in range(config.moe_experts)
            )
            self.output_norm = nn.LayerNorm(width)
            self.onset_head = nn.Linear(width, class_count)
            self.velocity_head = nn.Sequential(nn.Linear(width, class_count), nn.Sigmoid())

        def forward(self, features):
            encoded = self.encoder(features.transpose(1, 2)).transpose(1, 2)
            contextual, _ = self.temporal(encoded)
            router_logits = self.router(contextual)
            top_values, top_indices = torch.topk(router_logits, k=config.moe_top_k, dim=-1)
            top_weights = torch.softmax(top_values, dim=-1)
            weights = torch.zeros_like(router_logits).scatter(-1, top_indices, top_weights)
            expert_outputs = torch.stack([expert(contextual) for expert in self.experts], dim=-2)
            routed = (expert_outputs * weights.unsqueeze(-1)).sum(dim=-2)
            output = self.output_norm(contextual + routed)
            return self.onset_head(output), self.velocity_head(output)

    if config.architecture == "spectral_moe":
        return SpectralMoEDrumOnsetNetwork()
    return DrumOnsetNetwork()


def experiment_metadata(
    config: TrainingConfig,
    dataset_payload: dict[str, Any],
    *,
    prepared_dataset_sha256: str | None = None,
) -> dict[str, Any]:
    commit = "unknown"
    with suppress(OSError, subprocess.CalledProcessError):
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    metadata = {
        "schemaVersion": 1,
        "experimentId": str(uuid.uuid4()),
        "createdAt": datetime.now(UTC).isoformat(),
        "gitCommit": commit,
        "datasetVersion": dataset_payload.get("dataset"),
        "datasetManifestHash": dataset_payload.get("datasetManifestHash"),
        "modelVersion": config.model_version,
        "classes": [item.value for item in TRAINING_CLASSES],
        "configuration": asdict(config),
    }
    if prepared_dataset_sha256:
        metadata["preparedDatasetSha256"] = prepared_dataset_sha256
    if dataset_payload.get("pilotSelection"):
        metadata["pilotSelection"] = dataset_payload["pilotSelection"]
    if dataset_payload.get("oneShotOverlay"):
        metadata["oneShotOverlay"] = dataset_payload["oneShotOverlay"]
    return metadata


def run_training(config: TrainingConfig) -> Path:
    """Train a CRNN onset/velocity model and emit versioned reproducibility metadata."""
    try:
        import torch
        import torch.nn.functional as functional
    except ImportError as exc:  # pragma: no cover - exercised only with training extra
        raise TrainingError("install the 'train' extra before running training") from exc

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    device = _training_device(torch, config.device)
    prepared_path = Path(config.prepared_dataset).resolve()
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    if payload.get("evaluationOnly"):
        raise TrainingError("evaluation-only datasets cannot be used for training")
    prepared_dataset_sha256 = _sha256(prepared_path)
    records = payload.get("records", [])
    train_records = [record for record in records if record["split"] == "train"]
    validation_records = [record for record in records if record["split"] == "validation"]
    if not train_records or not validation_records:
        raise TrainingError("prepared data needs non-empty train and validation splits")

    first_features = np.load(train_records[0]["featurePath"])["features"]
    model = build_model(
        config,
        mel_bands=int(first_features.shape[1]),
        class_count=len(TRAINING_CLASSES),
    )
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer,
        mode="max",
        factor=config.lr_decay_factor,
        patience=config.lr_decay_patience,
        min_lr=config.minimum_learning_rate,
    )
    positive_weights = torch.from_numpy(_positive_class_weights(train_records)).to(device)
    start_epoch = 0
    best_f1 = -1.0
    best_thresholds: dict[str, float] = {}
    best_per_class: dict[str, float] = {}
    resumed_state: dict[str, Any] | None = None
    resume_provenance: dict[str, Any] | None = None
    if config.resume_checkpoint:
        resume_path = Path(config.resume_checkpoint).resolve()
        checkpoint = torch.load(resume_path, map_location=device, weights_only=True)
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        validation_compatible = _resume_validation_compatible(
            checkpoint,
            prepared_path=prepared_path,
            prepared_dataset_sha256=prepared_dataset_sha256,
        )
        if (
            validation_compatible
            and config.resume_learning_rate is None
            and checkpoint.get("scheduler")
        ):
            scheduler.load_state_dict(checkpoint["scheduler"])
        if config.resume_learning_rate is not None:
            for parameter_group in optimizer.param_groups:
                parameter_group["lr"] = config.resume_learning_rate
        start_epoch = int(checkpoint["epoch"]) + 1
        if validation_compatible:
            resumed_state = checkpoint
            best_f1 = float(checkpoint.get("bestF1", -1))
            best_thresholds = dict(checkpoint.get("validationThresholds", {}))
            best_per_class = dict(checkpoint.get("validationPerClassF1", {}))
        resume_provenance = {
            "checkpointSha256": _sha256(resume_path),
            "checkpointEpoch": int(checkpoint["epoch"]),
            "validationState": "carried" if validation_compatible else "reset",
        }
        if config.resume_learning_rate is not None:
            resume_provenance["learningRateOverride"] = config.resume_learning_rate

    output = Path(config.output_root).resolve() / config.model_version
    output.mkdir(parents=True, exist_ok=False)
    metadata = experiment_metadata(
        config,
        payload,
        prepared_dataset_sha256=prepared_dataset_sha256,
    )
    if resume_provenance:
        metadata["resume"] = resume_provenance
    (output / "experiment.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metrics_path = output / "metrics.jsonl"
    best_checkpoint = output / "best.pt"
    if resumed_state is not None:
        torch.save(resumed_state, best_checkpoint)
    stale_epochs = 0
    for epoch in range(start_epoch, config.epochs):
        model.train()
        train_losses = []
        for record in _epoch_records(train_records, seed=config.seed, epoch=epoch):
            features, onset_targets, velocity_targets = _load_training_record(record)
            for (
                feature_batch,
                onset_batch,
                velocity_batch,
                valid_batch,
            ) in _training_batches(
                features,
                onset_targets,
                velocity_targets,
                config.window_frames,
                config.batch_size,
            ):
                onset_logits, velocity = model(torch.from_numpy(feature_batch).to(device))
                original_onsets = torch.from_numpy(onset_batch).to(device)
                loss_onsets = torch.from_numpy(
                    _dilate_batched_targets(onset_batch, config.onset_tolerance_frames)
                ).to(device)
                velocity_tensor = torch.from_numpy(velocity_batch).to(device)
                valid_tensor = torch.from_numpy(valid_batch).to(device)
                onset_losses = functional.binary_cross_entropy_with_logits(
                    onset_logits,
                    loss_onsets,
                    pos_weight=positive_weights,
                    reduction="none",
                )
                onset_loss = (onset_losses * valid_tensor).sum() / (
                    valid_tensor.sum() * len(TRAINING_CLASSES)
                )
                mask = original_onsets > 0
                velocity_loss = (
                    functional.mse_loss(velocity[mask], velocity_tensor[mask])
                    if mask.any()
                    else velocity.sum() * 0
                )
                loss = onset_loss + velocity_loss * 0.25
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                optimizer.step()
                train_losses.append(float(loss.detach()))
        validation = _validation_metrics(
            model,
            validation_records,
            tolerance_frames=config.onset_tolerance_frames,
            device=device,
        )
        validation_f1 = float(validation["macroF1"])
        learning_rate = float(optimizer.param_groups[0]["lr"])
        scheduler.step(validation_f1)
        metrics = {
            "epoch": epoch,
            "trainLoss": sum(train_losses) / len(train_losses),
            "validationMacroF1": validation_f1,
            "validationThresholds": validation["thresholds"],
            "validationPerClassF1": validation["perClassF1"],
            "learningRate": learning_rate,
            "nextLearningRate": float(optimizer.param_groups[0]["lr"]),
        }
        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(metrics, sort_keys=True) + "\n")
        state = {
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "bestF1": max(best_f1, validation_f1),
            "configuration": asdict(config),
            "validationThresholds": validation["thresholds"],
            "validationPerClassF1": validation["perClassF1"],
            "preparedDatasetSha256": prepared_dataset_sha256,
        }
        torch.save(state, output / f"checkpoint-{epoch:04d}.pt")
        if validation_f1 > best_f1:
            best_f1 = validation_f1
            best_thresholds = dict(validation["thresholds"])
            best_per_class = dict(validation["perClassF1"])
            stale_epochs = 0
            torch.save(state, best_checkpoint)
        else:
            stale_epochs += 1
            if stale_epochs >= config.early_stopping_patience:
                break
    digest = hashlib.sha256(best_checkpoint.read_bytes()).hexdigest()
    metadata.update(
        {
            "modelSha256": digest,
            "bestValidationMacroF1": best_f1,
            "validationThresholds": best_thresholds,
            "validationPerClassF1": best_per_class,
        }
    )
    (output / "experiment.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _epoch_records(records: list[dict[str, Any]], *, seed: int, epoch: int) -> list[dict[str, Any]]:
    """Return a deterministic epoch-specific order without mutating the manifest list."""
    return sorted(
        records,
        key=lambda record: (
            hashlib.sha256(
                (
                    f"{seed}\0{epoch}\0{record.get('groupId', '')}\0"
                    f"{record.get('trackId', '')}\0{record.get('variant', '')}"
                ).encode()
            ).digest(),
            str(record.get("trackId", "")),
            str(record.get("variant", "")),
        ),
    )


def _resume_validation_compatible(
    checkpoint: dict[str, Any], *, prepared_path: Path, prepared_dataset_sha256: str
) -> bool:
    checkpoint_hash = checkpoint.get("preparedDatasetSha256")
    if checkpoint_hash:
        return checkpoint_hash == prepared_dataset_sha256
    checkpoint_dataset = checkpoint.get("configuration", {}).get("prepared_dataset")
    return bool(checkpoint_dataset) and Path(checkpoint_dataset).resolve() == prepared_path


def _load_training_record(record: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cache = np.load(record["featurePath"])
    features = cache["features"].astype(np.float32)
    hop_length = int(cache["hop_length"])
    sample_rate = int(cache["sample_rate"])
    events = json.loads(Path(record["annotationPath"]).read_text(encoding="utf-8"))["events"]
    targets = np.zeros((len(features), len(TRAINING_CLASSES)), dtype=np.float32)
    velocities = np.zeros_like(targets)
    class_index = {instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)}
    for event in events:
        if event["instrument"] not in class_index:
            continue
        frame = min(len(features) - 1, round(event["onsetSeconds"] * sample_rate / hop_length))
        index = class_index[event["instrument"]]
        targets[frame, index] = 1
        velocities[frame, index] = event["velocity"] / 127
    return features, targets, velocities


def _validation_f1(
    model,
    records: list[dict[str, Any]],
    *,
    tolerance_frames: int = 2,
    device: str = "cpu",
) -> float:
    return float(
        _validation_metrics(
            model,
            records,
            tolerance_frames=tolerance_frames,
            device=device,
        )["macroF1"]
    )


def _validation_metrics(
    model,
    records: list[dict[str, Any]],
    *,
    tolerance_frames: int = 2,
    device: str = "cpu",
) -> dict[str, Any]:
    import torch

    evaluated: list[tuple[np.ndarray, np.ndarray]] = []
    model.eval()
    with torch.no_grad():
        for record in records:
            features, targets, _ = _load_training_record(record)
            logits, _ = model(torch.from_numpy(features)[None].to(device))
            probabilities = torch.sigmoid(logits)[0].cpu().numpy()
            evaluated.append((probabilities, targets))

    threshold_candidates = np.linspace(0.05, 0.95, 19)
    thresholds: dict[str, float] = {}
    per_class: dict[str, float] = {}
    for index, instrument in enumerate(TRAINING_CLASSES):
        support = sum(int(targets[:, index].sum()) for _, targets in evaluated)
        if not support:
            thresholds[instrument.value] = 0.99
            continue
        candidates: list[tuple[float, float]] = []
        for threshold in threshold_candidates:
            true_positive = false_positive = false_negative = 0
            for probabilities, targets in evaluated:
                references = np.flatnonzero(targets[:, index] > 0).tolist()
                predictions = _peak_frames(probabilities[:, index], threshold=float(threshold))
                tp, fp, fn = _match_frames(
                    references,
                    predictions,
                    tolerance=tolerance_frames,
                )
                true_positive += tp
                false_positive += fp
                false_negative += fn
            denominator = 2 * true_positive + false_positive + false_negative
            score = 2 * true_positive / denominator if denominator else 0.0
            candidates.append((score, float(threshold)))
        score, threshold = max(candidates, key=lambda item: (item[0], -abs(item[1] - 0.5)))
        thresholds[instrument.value] = threshold
        per_class[instrument.value] = score
    macro_f1 = sum(per_class.values()) / len(per_class) if per_class else 0.0
    return {"macroF1": macro_f1, "thresholds": thresholds, "perClassF1": per_class}


def _positive_class_weights(records: list[dict[str, Any]]) -> np.ndarray:
    positive = np.zeros(len(TRAINING_CLASSES), dtype=np.float64)
    frame_count = 0
    for record in records:
        _, targets, _ = _load_training_record(record)
        positive += targets.sum(axis=0)
        frame_count += len(targets)
    negative = frame_count - positive
    return np.where(positive > 0, np.clip(negative / np.maximum(positive, 1), 1, 100), 1).astype(
        np.float32
    )


def _dilate_targets(targets: np.ndarray, tolerance: int) -> np.ndarray:
    if tolerance <= 0:
        return targets.copy()
    output = targets.copy()
    for shift in range(1, tolerance + 1):
        output[shift:] = np.maximum(output[shift:], targets[:-shift])
        output[:-shift] = np.maximum(output[:-shift], targets[shift:])
    return output


def _training_batches(
    features: np.ndarray,
    onsets: np.ndarray,
    velocities: np.ndarray,
    window_frames: int,
    batch_size: int,
):
    windows = [
        (
            features[start : start + window_frames],
            onsets[start : start + window_frames],
            velocities[start : start + window_frames],
        )
        for start in range(0, len(features), window_frames)
    ]
    for batch_start in range(0, len(windows), batch_size):
        batch = windows[batch_start : batch_start + batch_size]
        maximum = max(len(window[0]) for window in batch)
        feature_batch = np.zeros((len(batch), maximum, features.shape[1]), dtype=np.float32)
        onset_batch = np.zeros((len(batch), maximum, onsets.shape[1]), dtype=np.float32)
        velocity_batch = np.zeros_like(onset_batch)
        valid_batch = np.zeros((len(batch), maximum, 1), dtype=np.float32)
        for index, (feature_window, onset_window, velocity_window) in enumerate(batch):
            length = len(feature_window)
            feature_batch[index, :length] = feature_window
            onset_batch[index, :length] = onset_window
            velocity_batch[index, :length] = velocity_window
            valid_batch[index, :length] = 1
        yield feature_batch, onset_batch, velocity_batch, valid_batch


def _dilate_batched_targets(targets: np.ndarray, tolerance: int) -> np.ndarray:
    return np.stack([_dilate_targets(row, tolerance) for row in targets])


def _peak_frames(probabilities: np.ndarray, *, threshold: float) -> list[int]:
    if not len(probabilities):
        return []
    padded = np.pad(probabilities, (1, 1), constant_values=-np.inf)
    return np.flatnonzero(
        (probabilities >= threshold) & (probabilities >= padded[:-2]) & (probabilities > padded[2:])
    ).tolist()


def _match_frames(
    references: list[int], predictions: list[int], *, tolerance: int
) -> tuple[int, int, int]:
    reference_index = prediction_index = true_positive = 0
    while reference_index < len(references) and prediction_index < len(predictions):
        delta = predictions[prediction_index] - references[reference_index]
        if delta < -tolerance:
            prediction_index += 1
        elif delta > tolerance:
            reference_index += 1
        else:
            true_positive += 1
            reference_index += 1
            prediction_index += 1
    return (
        true_positive,
        len(predictions) - true_positive,
        len(references) - true_positive,
    )


def _training_device(torch, requested: str) -> str:
    if requested != "auto":
        if requested == "cuda" and not torch.cuda.is_available():
            raise TrainingError("CUDA was requested but is unavailable")
        if requested == "mps" and not torch.backends.mps.is_available():
            raise TrainingError("MPS was requested but is unavailable")
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"
