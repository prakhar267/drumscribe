"""Temporal calibration over aligned drum-onset probability streams."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .training import TRAINING_CLASSES, TrainingError, _peak_frames

DEFAULT_SOURCE_ORDER = (
    "stemEnsemble",
    "stemSpecialist",
    "mixtureEnsemble",
    "mixtureSpecialist",
)
FusionMode = Literal["base", "stacker", "union", "intersection"]
Event = tuple[float, str]


@dataclass(frozen=True, slots=True)
class StackerDecoderRule:
    threshold: float
    peak_distance_frames: int
    onset_shift_frames: int = 0

    def __post_init__(self) -> None:
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise TrainingError("stacker threshold must be between zero and one")
        if self.peak_distance_frames < 1:
            raise TrainingError("stacker peak distance must be positive")


@dataclass(frozen=True, slots=True)
class EventFusionRule:
    mode: FusionMode
    radius_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.mode not in {"base", "stacker", "union", "intersection"}:
            raise TrainingError(f"unsupported event fusion mode: {self.mode}")
        if not math.isfinite(self.radius_seconds) or self.radius_seconds < 0:
            raise TrainingError("event fusion radius must be finite and non-negative")
        if self.mode in {"union", "intersection"} and self.radius_seconds <= 0:
            raise TrainingError(f"{self.mode} fusion needs a positive radius")


def temporal_context_features(
    probability_sources: dict[str, np.ndarray],
    *,
    source_order: tuple[str, ...] = DEFAULT_SOURCE_ORDER,
    offsets: tuple[int, ...] = (-6, -4, -2, 0, 2, 4, 6),
    clip_epsilon: float = 1e-5,
) -> np.ndarray:
    """Return frame-aligned temporal logits for a compact learned stacker."""
    if not source_order or not offsets:
        raise TrainingError("temporal stacker sources and offsets cannot be empty")
    if not 0 < clip_epsilon < 0.5:
        raise TrainingError("temporal stacker clip epsilon must be in (0, 0.5)")
    missing = sorted(set(source_order) - set(probability_sources))
    if missing:
        raise TrainingError(f"missing temporal stacker probability sources: {missing}")
    shapes = {probability_sources[name].shape for name in source_order}
    if len(shapes) != 1:
        raise TrainingError("temporal stacker probability sources must align")
    shape = next(iter(shapes))
    if len(shape) != 2 or shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("temporal stacker sources must be frame-by-canonical-class")
    if any(
        not np.isfinite(probability_sources[name]).all()
        or np.any(probability_sources[name] < 0)
        or np.any(probability_sources[name] > 1)
        for name in source_order
    ):
        raise TrainingError("temporal stacker probabilities must be finite and in [0, 1]")

    frame_indices = np.arange(shape[0])
    features: list[np.ndarray] = []
    for name in source_order:
        probability = np.clip(
            probability_sources[name].astype(np.float32),
            clip_epsilon,
            1 - clip_epsilon,
        )
        logits = np.log(probability) - np.log1p(-probability)
        for offset in offsets:
            indices = np.clip(frame_indices + offset, 0, shape[0] - 1)
            features.append(logits[indices])
    return np.concatenate(features, axis=1).astype(np.float32)


def build_temporal_stacker(
    input_size: int,
    *,
    class_count: int = len(TRAINING_CLASSES),
    hidden_sizes: tuple[int, int] = (256, 128),
    dropout: float = 0.15,
):
    """Build the small framewise MLP used for temporal probability calibration."""
    try:
        import torch.nn as nn
    except ImportError as exc:  # pragma: no cover - training dependency guard
        raise TrainingError("install the training dependencies to build the stacker") from exc
    if input_size < 1 or class_count < 1 or any(size < 1 for size in hidden_sizes):
        raise TrainingError("temporal stacker dimensions must be positive")
    if not 0 <= dropout < 1:
        raise TrainingError("temporal stacker dropout must be in [0, 1)")
    return nn.Sequential(
        nn.Linear(input_size, hidden_sizes[0]),
        nn.LayerNorm(hidden_sizes[0]),
        nn.GELU(),
        nn.Dropout(dropout),
        nn.Linear(hidden_sizes[0], hidden_sizes[1]),
        nn.GELU(),
        nn.Linear(hidden_sizes[1], class_count),
    )


def decode_stacker_probabilities(
    probabilities: np.ndarray,
    rules: dict[str, StackerDecoderRule],
) -> dict[str, list[int]]:
    """Decode class peaks and apply frozen class-specific frame alignment."""
    if probabilities.ndim != 2 or probabilities.shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("stacker probabilities must be frame-by-canonical-class")
    expected = {instrument.value for instrument in TRAINING_CLASSES}
    if set(rules) != expected:
        raise TrainingError("stacker decoder rules must cover every canonical class")
    decoded: dict[str, list[int]] = {}
    for index, instrument in enumerate(TRAINING_CLASSES):
        rule = rules[instrument.value]
        frames = _peak_frames(
            probabilities[:, index],
            threshold=rule.threshold,
            minimum_distance_frames=rule.peak_distance_frames,
        )
        decoded[instrument.value] = [
            frame + rule.onset_shift_frames
            for frame in frames
            if 0 <= frame + rule.onset_shift_frames < len(probabilities)
        ]
    return decoded


def fuse_event_streams(
    base_events: list[Event],
    stacker_events: list[Event],
    rules: dict[str, EventFusionRule],
) -> list[Event]:
    """Fuse two decoded event streams with fixed per-instrument policies."""
    expected = {instrument.value for instrument in TRAINING_CLASSES}
    if set(rules) != expected:
        raise TrainingError("event fusion rules must cover every canonical class")
    fused: list[Event] = []
    for instrument in TRAINING_CLASSES:
        name = instrument.value
        rule = rules[name]
        base = sorted(onset for onset, label in base_events if label == name)
        stacker = sorted(onset for onset, label in stacker_events if label == name)
        if rule.mode == "base":
            selected = base
        elif rule.mode == "stacker":
            selected = stacker
        elif rule.mode == "intersection":
            selected = [
                onset
                for onset in base
                if any(abs(onset - candidate) <= rule.radius_seconds for candidate in stacker)
            ]
        else:
            selected = list(base)
            for onset in stacker:
                if not any(abs(onset - candidate) <= rule.radius_seconds for candidate in selected):
                    selected.append(onset)
            selected.sort()
        fused.extend((onset, name) for onset in selected)
    return sorted(fused)
