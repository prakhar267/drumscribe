"""Pure-NumPy runtime for DrumScribe's kit-adaptive multi-label detector.

The detector deliberately keeps training-only PyTorch out of the serving path.
It consumes the same cached log-mel representation as the self-hosted CRNNs,
discovers dense broadband attacks, and emits every drum class whose calibrated
probability clears its validation threshold.  Emitting multiple labels for one
attack is essential for kick/cymbal/snare layers.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_music import Instrument

from .lifecycle import PreparationConfig, cache_log_mel
from .training import TRAINING_CLASSES, TrainingError, _peak_frames

MODEL_SCHEMA_VERSION = 1
SAMPLE_RATE = 22_050
HOP_LENGTH = 220
FEATURE_FRAMES = 12
MEL_BANDS = 80
FEATURE_WIDTH = FEATURE_FRAMES * MEL_BANDS * 2
DEFAULT_FLUX_QUANTILE = 0.46
DEFAULT_PEAK_DISTANCE_FRAMES = 6

EXCLUSIVE_FAMILIES = (
    (Instrument.CLOSED_HIHAT, Instrument.OPEN_HIHAT, Instrument.PEDAL_HIHAT),
    (Instrument.RIDE, Instrument.RIDE_BELL),
)


@dataclass(frozen=True, slots=True)
class KitAdapterPrediction:
    instrument: Instrument
    frame: int
    confidence: float
    velocity: int

    @property
    def onset_seconds(self) -> float:
        return self.frame * HOP_LENGTH / SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class KitAdapterModel:
    model_version: str
    classes: tuple[Instrument, ...]
    thresholds: np.ndarray
    feature_mean: np.ndarray
    feature_std: np.ndarray
    w1: np.ndarray
    b1: np.ndarray
    layer_norm_weight: np.ndarray
    layer_norm_bias: np.ndarray
    w2: np.ndarray
    b2: np.ndarray
    w3: np.ndarray
    b3: np.ndarray
    flux_quantile: float = DEFAULT_FLUX_QUANTILE
    peak_distance_frames: int = DEFAULT_PEAK_DISTANCE_FRAMES
    class_peak_distance_frames: np.ndarray = field(
        default_factory=lambda: np.ones(len(TRAINING_CLASSES), dtype=np.int32)
    )

    @classmethod
    def load(cls, path: Path) -> KitAdapterModel:
        source = Path(path).resolve(strict=True)
        with np.load(source, allow_pickle=False) as arrays:
            required = {
                "schema_version",
                "model_version",
                "classes",
                "thresholds",
                "feature_mean",
                "feature_std",
                "w1",
                "b1",
                "layer_norm_weight",
                "layer_norm_bias",
                "w2",
                "b2",
                "w3",
                "b3",
                "flux_quantile",
                "peak_distance_frames",
            }
            missing = sorted(required - set(arrays.files))
            if missing:
                raise TrainingError(f"kit-adapter model is missing arrays: {missing}")
            schema_version = int(np.asarray(arrays["schema_version"]).item())
            if schema_version != MODEL_SCHEMA_VERSION:
                raise TrainingError(
                    f"unsupported kit-adapter schema {schema_version}; "
                    f"expected {MODEL_SCHEMA_VERSION}"
                )
            classes = tuple(
                Instrument(str(value)) for value in np.asarray(arrays["classes"]).tolist()
            )
            model = cls(
                model_version=str(np.asarray(arrays["model_version"]).item()),
                classes=classes,
                thresholds=np.asarray(arrays["thresholds"], dtype=np.float32),
                feature_mean=np.asarray(arrays["feature_mean"], dtype=np.float32),
                feature_std=np.asarray(arrays["feature_std"], dtype=np.float32),
                w1=np.asarray(arrays["w1"], dtype=np.float32),
                b1=np.asarray(arrays["b1"], dtype=np.float32),
                layer_norm_weight=np.asarray(arrays["layer_norm_weight"], dtype=np.float32),
                layer_norm_bias=np.asarray(arrays["layer_norm_bias"], dtype=np.float32),
                w2=np.asarray(arrays["w2"], dtype=np.float32),
                b2=np.asarray(arrays["b2"], dtype=np.float32),
                w3=np.asarray(arrays["w3"], dtype=np.float32),
                b3=np.asarray(arrays["b3"], dtype=np.float32),
                flux_quantile=float(np.asarray(arrays["flux_quantile"]).item()),
                peak_distance_frames=int(np.asarray(arrays["peak_distance_frames"]).item()),
                class_peak_distance_frames=(
                    np.asarray(arrays["class_peak_distance_frames"], dtype=np.int32)
                    if "class_peak_distance_frames" in arrays
                    else np.ones(len(TRAINING_CLASSES), dtype=np.int32)
                ),
            )
        model._validate()
        return model

    def _validate(self) -> None:
        if self.classes != TRAINING_CLASSES:
            raise TrainingError("kit-adapter classes do not match the canonical class order")
        class_count = len(self.classes)
        hidden_one = self.b1.shape[0]
        hidden_two = self.b2.shape[0]
        expected_shapes = {
            "thresholds": (class_count,),
            "feature_mean": (FEATURE_WIDTH,),
            "feature_std": (FEATURE_WIDTH,),
            "class_peak_distance_frames": (class_count,),
            "w1": (hidden_one, FEATURE_WIDTH),
            "layer_norm_weight": (hidden_one,),
            "layer_norm_bias": (hidden_one,),
            "w2": (hidden_two, hidden_one),
            "w3": (class_count, hidden_two),
            "b3": (class_count,),
        }
        for name, expected in expected_shapes.items():
            if getattr(self, name).shape != expected:
                raise TrainingError(
                    f"kit-adapter array {name} has shape {getattr(self, name).shape}; "
                    f"expected {expected}"
                )
        arrays = (
            self.thresholds,
            self.feature_mean,
            self.feature_std,
            self.w1,
            self.b1,
            self.layer_norm_weight,
            self.layer_norm_bias,
            self.w2,
            self.b2,
            self.w3,
            self.b3,
        )
        if any(not np.isfinite(array).all() for array in arrays):
            raise TrainingError("kit-adapter model arrays must be finite")
        if np.any(self.feature_std <= 0):
            raise TrainingError("kit-adapter feature standard deviations must be positive")
        if np.any(self.thresholds <= 0) or np.any(self.thresholds >= 1):
            raise TrainingError("kit-adapter thresholds must lie strictly between zero and one")
        if np.any(self.class_peak_distance_frames < 1):
            raise TrainingError("class peak distances must be positive")
        if not 0 < self.flux_quantile < 1 or self.peak_distance_frames < 1:
            raise TrainingError("kit-adapter onset settings are invalid")

    def probabilities(self, vectors: np.ndarray) -> np.ndarray:
        if vectors.ndim != 2 or vectors.shape[1] != FEATURE_WIDTH:
            raise TrainingError(f"kit-adapter vectors must have shape (frames, {FEATURE_WIDTH})")
        normalized = (vectors.astype(np.float32) - self.feature_mean) / self.feature_std
        hidden = normalized @ self.w1.T + self.b1
        mean = hidden.mean(axis=1, keepdims=True)
        variance = hidden.var(axis=1, keepdims=True)
        hidden = (hidden - mean) / np.sqrt(
            variance + 1e-5
        ) * self.layer_norm_weight + self.layer_norm_bias
        hidden = _gelu(hidden)
        hidden = _gelu(hidden @ self.w2.T + self.b2)
        logits = hidden @ self.w3.T + self.b3
        return 1 / (1 + np.exp(-np.clip(logits, -40, 40)))


def dense_transient_frames(
    features: np.ndarray,
    *,
    flux_quantile: float = DEFAULT_FLUX_QUANTILE,
    minimum_distance_frames: int = DEFAULT_PEAK_DISTANCE_FRAMES,
) -> list[int]:
    """Find closely spaced attacks without assuming a tempo or meter."""

    if features.ndim != 2 or features.shape[1] != MEL_BANDS:
        raise TrainingError("onset features must be a frame-by-80-band matrix")
    if not len(features):
        return []
    high_band = features[:, 30:]
    positive_delta = np.maximum(
        0,
        np.diff(high_band, axis=0, prepend=high_band[:1]),
    )
    flux = positive_delta.sum(axis=1)
    threshold = max(
        float(np.quantile(flux, flux_quantile)),
        float(np.nextafter(np.float32(0), np.float32(1))),
    )
    return _peak_frames(
        flux,
        threshold=threshold,
        minimum_distance_frames=minimum_distance_frames,
    )


def candidate_vectors(features: np.ndarray, frames: list[int]) -> np.ndarray:
    """Build attack-aware absolute+delta features for candidate frames."""

    if not frames:
        return np.empty((0, FEATURE_WIDTH), dtype=np.float32)
    vectors = []
    maximum_start = max(1, len(features) - FEATURE_FRAMES - 1)
    for frame in frames:
        start = max(1, min(maximum_start, int(frame) - 1))
        absolute = features[start : start + FEATURE_FRAMES]
        previous = features[start - 1 : start + FEATURE_FRAMES - 1]
        if absolute.shape != (FEATURE_FRAMES, MEL_BANDS):
            absolute = np.pad(
                absolute,
                ((0, FEATURE_FRAMES - len(absolute)), (0, 0)),
            )
            previous = np.pad(
                previous,
                ((0, FEATURE_FRAMES - len(previous)), (0, 0)),
            )
        delta = np.maximum(0, absolute - previous)
        absolute = np.log1p(absolute)
        absolute = (absolute - absolute.mean()) / (absolute.std() + 1e-5)
        delta = delta / (delta.max() + 1e-5)
        vectors.append(np.concatenate((absolute, delta), axis=1).reshape(-1))
    return np.asarray(vectors, dtype=np.float32)


def predict_features(
    features: np.ndarray,
    model: KitAdapterModel,
) -> list[KitAdapterPrediction]:
    frames = dense_transient_frames(
        features,
        flux_quantile=model.flux_quantile,
        minimum_distance_frames=model.peak_distance_frames,
    )
    probabilities = model.probabilities(candidate_vectors(features, frames))
    selected = probabilities >= model.thresholds
    class_index = {instrument: index for index, instrument in enumerate(model.classes)}
    for row in range(len(frames)):
        for family in EXCLUSIVE_FAMILIES:
            indices = [class_index[instrument] for instrument in family]
            active = [index for index in indices if selected[row, index]]
            if len(active) > 1:
                winner = max(active, key=lambda index: float(probabilities[row, index]))
                selected[row, active] = False
                selected[row, winner] = True

    # Dense candidate generation deliberately favors recall. Suppress nearby
    # duplicate emissions independently for each instrument after classification.
    for class_index in range(len(model.classes)):
        active_rows = np.flatnonzero(selected[:, class_index])
        ordered = active_rows[np.argsort(-probabilities[active_rows, class_index])]
        kept: list[int] = []
        minimum_distance = int(model.class_peak_distance_frames[class_index])
        for row in ordered:
            if all(abs(frames[int(row)] - frames[other]) >= minimum_distance for other in kept):
                kept.append(int(row))
        selected[active_rows, class_index] = False
        selected[kept, class_index] = True

    predictions: list[KitAdapterPrediction] = []
    for row, frame in enumerate(frames):
        frame_energy = float(np.max(features[max(0, frame - 1) : frame + 2]))
        for index in np.flatnonzero(selected[row]):
            confidence = float(probabilities[row, index])
            velocity = max(
                20,
                min(127, round(34 + 68 * confidence + 6 * math.log1p(frame_energy))),
            )
            predictions.append(
                KitAdapterPrediction(
                    instrument=model.classes[int(index)],
                    frame=frame,
                    confidence=confidence,
                    velocity=velocity,
                )
            )
    predictions.sort(key=lambda item: (item.frame, item.instrument.value))
    return predictions


def transcribe_wav(path: Path, model: KitAdapterModel) -> list[KitAdapterPrediction]:
    source = Path(path).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="drumscribe-kit-adapter-") as directory:
        feature_path = Path(directory) / "features.npz"
        cache_log_mel(
            source,
            feature_path,
            PreparationConfig(seed="kit-adapter-inference", augmentation_variants=0),
        )
        with np.load(feature_path, allow_pickle=False) as arrays:
            features = np.asarray(arrays["features"], dtype=np.float32)
    return predict_features(features, model)


def model_manifest(path: Path) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    model = KitAdapterModel.load(source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "schemaVersion": MODEL_SCHEMA_VERSION,
        "modelVersion": model.model_version,
        "sha256": digest,
        "classes": [instrument.value for instrument in model.classes],
        "fluxQuantile": model.flux_quantile,
        "peakDistanceFrames": model.peak_distance_frames,
        "classPeakDistanceFrames": {
            instrument.value: int(model.class_peak_distance_frames[index])
            for index, instrument in enumerate(model.classes)
        },
        "thresholds": {
            instrument.value: float(model.thresholds[index])
            for index, instrument in enumerate(model.classes)
        },
    }


def write_manifest(path: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(model_manifest(path), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def _gelu(values: np.ndarray) -> np.ndarray:
    # Fast tanh approximation used by many serving runtimes.  Training export
    # calibrates thresholds through this exact NumPy path.
    return (
        0.5
        * values
        * (1 + np.tanh(math.sqrt(2 / math.pi) * (values + 0.044715 * np.power(values, 3))))
    )
