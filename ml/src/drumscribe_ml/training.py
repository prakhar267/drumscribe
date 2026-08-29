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
from typing import Any

import numpy as np
from drumscribe_music import Instrument


class TrainingError(RuntimeError):
    pass


TRAINING_CLASSES = (
    Instrument.KICK,
    Instrument.SNARE,
    Instrument.CLOSED_HIHAT,
    Instrument.OPEN_HIHAT,
    Instrument.RIDE,
    Instrument.CRASH,
    Instrument.HIGH_TOM,
    Instrument.MID_TOM,
    Instrument.LOW_TOM,
    Instrument.FLOOR_TOM,
)


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
    seed: int = 20260829
    resume_checkpoint: str | None = None

    def __post_init__(self) -> None:
        if not self.model_version.strip() or "/" in self.model_version:
            raise TrainingError("model_version must be a non-empty filesystem-safe version")
        if self.epochs < 1 or self.early_stopping_patience < 1 or self.hidden_size < 16:
            raise TrainingError("epochs, patience, and hidden size must be positive")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise TrainingError("learning_rate must be positive and finite")
        if not 0 <= self.dropout < 1:
            raise TrainingError("dropout must be between zero and one")

    @classmethod
    def load(cls, path: Path) -> TrainingConfig:
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def build_model(config: TrainingConfig, *, mel_bands: int, class_count: int):
    try:
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

    return DrumOnsetNetwork()


def experiment_metadata(config: TrainingConfig, dataset_payload: dict[str, Any]) -> dict[str, Any]:
    commit = "unknown"
    with suppress(OSError, subprocess.CalledProcessError):
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    return {
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


def run_training(config: TrainingConfig) -> Path:
    """Train a CRNN onset/velocity model and emit versioned reproducibility metadata."""
    try:
        import torch
        import torch.nn.functional as functional
    except ImportError as exc:  # pragma: no cover - exercised only with training extra
        raise TrainingError("install the 'train' extra before running training") from exc

    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    prepared_path = Path(config.prepared_dataset).resolve()
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
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
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    start_epoch = 0
    best_f1 = -1.0
    if config.resume_checkpoint:
        checkpoint = torch.load(config.resume_checkpoint, map_location="cpu", weights_only=True)
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_f1 = float(checkpoint.get("bestF1", -1))

    output = Path(config.output_root).resolve() / config.model_version
    output.mkdir(parents=True, exist_ok=False)
    metadata = experiment_metadata(config, payload)
    (output / "experiment.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    metrics_path = output / "metrics.jsonl"
    best_checkpoint = output / "best.pt"
    stale_epochs = 0
    for epoch in range(start_epoch, config.epochs):
        model.train()
        train_losses = []
        for record in train_records:
            features, onset_targets, velocity_targets = _load_training_record(record)
            onset_logits, velocity = model(torch.from_numpy(features)[None])
            onset_tensor = torch.from_numpy(onset_targets)[None]
            velocity_tensor = torch.from_numpy(velocity_targets)[None]
            onset_loss = functional.binary_cross_entropy_with_logits(onset_logits, onset_tensor)
            mask = onset_tensor > 0
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
        validation_f1 = _validation_f1(model, validation_records)
        metrics = {
            "epoch": epoch,
            "trainLoss": sum(train_losses) / len(train_losses),
            "validationMacroF1": validation_f1,
        }
        with metrics_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(metrics, sort_keys=True) + "\n")
        state = {
            "epoch": epoch,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "bestF1": max(best_f1, validation_f1),
            "configuration": asdict(config),
        }
        torch.save(state, output / f"checkpoint-{epoch:04d}.pt")
        if validation_f1 > best_f1:
            best_f1 = validation_f1
            stale_epochs = 0
            torch.save(state, best_checkpoint)
        else:
            stale_epochs += 1
            if stale_epochs >= config.early_stopping_patience:
                break
    digest = hashlib.sha256(best_checkpoint.read_bytes()).hexdigest()
    metadata.update({"modelSha256": digest, "bestValidationMacroF1": best_f1})
    (output / "experiment.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output


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


def _validation_f1(model, records: list[dict[str, Any]]) -> float:
    import torch

    scores: list[float] = []
    model.eval()
    with torch.no_grad():
        for record in records:
            features, targets, _ = _load_training_record(record)
            logits, _ = model(torch.from_numpy(features)[None])
            predictions = torch.sigmoid(logits)[0].numpy() >= 0.5
            for index in range(targets.shape[1]):
                truth = targets[:, index] > 0
                predicted = predictions[:, index]
                tp = int(np.logical_and(truth, predicted).sum())
                fp = int(np.logical_and(~truth, predicted).sum())
                fn = int(np.logical_and(truth, ~predicted).sum())
                denominator = 2 * tp + fp + fn
                if denominator:
                    scores.append(2 * tp / denominator)
    return sum(scores) / len(scores) if scores else 0.0
