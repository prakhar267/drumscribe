"""Deterministic probability fusion across drum-stem and full-mixture views."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .training import TRAINING_CLASSES, TrainingError, _peak_frames


@dataclass(frozen=True, slots=True)
class MultiViewRule:
    model_weights: dict[str, float]
    threshold: float
    peak_distance_frames: int

    def __post_init__(self) -> None:
        if not self.model_weights or any(not name.strip() for name in self.model_weights):
            raise TrainingError("multi-view rules require named probability sources")
        if any(not math.isfinite(weight) or weight < 0 for weight in self.model_weights.values()):
            raise TrainingError("multi-view weights must be finite and non-negative")
        if not math.isclose(sum(self.model_weights.values()), 1.0, abs_tol=1e-6):
            raise TrainingError("multi-view weights must sum to one")
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise TrainingError("multi-view thresholds must be between zero and one")
        if self.peak_distance_frames < 1:
            raise TrainingError("multi-view peak distance must be at least one frame")


@dataclass(frozen=True, slots=True)
class MultiViewConfig:
    model_version: str
    rules: dict[str, MultiViewRule]
    production_approved: bool = False

    def __post_init__(self) -> None:
        if not self.model_version.strip():
            raise TrainingError("multi-view model version must not be empty")
        expected = {instrument.value for instrument in TRAINING_CLASSES}
        actual = set(self.rules)
        if actual != expected:
            raise TrainingError(
                "multi-view rules must cover every class; "
                f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
            )

    @classmethod
    def load(cls, path: Path) -> MultiViewConfig:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if int(payload.get("schemaVersion", 0)) != 1:
            raise TrainingError("multi-view config requires schemaVersion 1")
        return cls(
            model_version=str(payload["modelVersion"]),
            production_approved=bool(payload.get("productionApproved", False)),
            rules={
                instrument: MultiViewRule(
                    model_weights={
                        str(name): float(weight) for name, weight in rule["modelWeights"].items()
                    },
                    threshold=float(rule["threshold"]),
                    peak_distance_frames=int(rule["peakDistanceFrames"]),
                )
                for instrument, rule in payload["rules"].items()
            },
        )


def blend_multiview_probabilities(
    probability_sources: dict[str, np.ndarray],
    rules: dict[str, MultiViewRule],
) -> np.ndarray:
    """Apply fixed per-class convex fusion to frame-aligned probability views."""
    if not probability_sources:
        raise TrainingError("multi-view probability sources cannot be empty")
    shapes = {probabilities.shape for probabilities in probability_sources.values()}
    if len(shapes) != 1:
        raise TrainingError("multi-view probability sources must have identical shapes")
    shape = next(iter(shapes))
    if len(shape) != 2 or shape[1] != len(TRAINING_CLASSES):
        raise TrainingError("multi-view probabilities must be frame-by-canonical-class")
    if any(
        not np.isfinite(probabilities).all()
        or np.any(probabilities < 0)
        or np.any(probabilities > 1)
        for probabilities in probability_sources.values()
    ):
        raise TrainingError("multi-view probabilities must be finite and between zero and one")

    output = np.empty(shape, dtype=np.float64)
    for index, instrument in enumerate(TRAINING_CLASSES):
        rule = rules[instrument.value]
        missing = sorted(set(rule.model_weights) - set(probability_sources))
        if missing:
            raise TrainingError(f"missing multi-view probability sources: {missing}")
        output[:, index] = sum(
            weight * probability_sources[name][:, index]
            for name, weight in rule.model_weights.items()
        )
    return output


def decode_multiview_probabilities(
    probability_sources: dict[str, np.ndarray],
    rules: dict[str, MultiViewRule],
) -> tuple[np.ndarray, dict[str, list[int]]]:
    """Blend the views and decode fixed local maxima for every instrument."""
    probabilities = blend_multiview_probabilities(probability_sources, rules)
    decoded = {
        instrument.value: _peak_frames(
            probabilities[:, index],
            threshold=rules[instrument.value].threshold,
            minimum_distance_frames=rules[instrument.value].peak_distance_frames,
        )
        for index, instrument in enumerate(TRAINING_CLASSES)
    }
    return probabilities, decoded


def config_evidence(path: Path) -> dict[str, Any]:
    """Return non-executable evidence metadata embedded beside fixed rules."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return {
        key: payload[key] for key in ("components", "calibration", "limitations") if key in payload
    }
