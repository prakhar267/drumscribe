"""Validation-set confidence calibration for multi-label drum onsets."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    temperature: float
    thresholds: tuple[float, ...]
    macro_f1: float


def sigmoid(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    if not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be positive and finite")
    scaled = np.clip(logits / temperature, -50, 50)
    return 1 / (1 + np.exp(-scaled))


def calibrate_confidence(
    logits: np.ndarray,
    targets: np.ndarray,
    *,
    temperature_candidates: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0),
    threshold_candidates: tuple[float, ...] = tuple(np.linspace(0.1, 0.9, 17)),
) -> CalibrationResult:
    if logits.shape != targets.shape or logits.ndim != 2:
        raise ValueError("logits and targets must be equally shaped [events, classes] arrays")
    if not len(logits) or not np.isin(targets, (0, 1)).all():
        raise ValueError("calibration requires non-empty binary targets")
    best_temperature = min(
        temperature_candidates,
        key=lambda value: _binary_cross_entropy(sigmoid(logits, value), targets),
    )
    probabilities = sigmoid(logits, best_temperature)
    thresholds: list[float] = []
    scores: list[float] = []
    for class_index in range(targets.shape[1]):
        class_target = targets[:, class_index]
        candidate, score = max(
            (
                (threshold, _f1(class_target, probabilities[:, class_index] >= threshold))
                for threshold in threshold_candidates
            ),
            key=lambda item: (item[1], -abs(item[0] - 0.5)),
        )
        thresholds.append(float(candidate))
        scores.append(score)
    return CalibrationResult(
        temperature=float(best_temperature),
        thresholds=tuple(thresholds),
        macro_f1=float(sum(scores) / len(scores)),
    )


def _binary_cross_entropy(probabilities: np.ndarray, targets: np.ndarray) -> float:
    bounded = np.clip(probabilities, 1e-7, 1 - 1e-7)
    return float(np.mean(-(targets * np.log(bounded) + (1 - targets) * np.log(1 - bounded))))


def _f1(targets: np.ndarray, predicted: np.ndarray) -> float:
    true_positive = int(np.logical_and(targets == 1, predicted).sum())
    false_positive = int(np.logical_and(targets == 0, predicted).sum())
    false_negative = int(np.logical_and(targets == 1, np.logical_not(predicted)).sum())
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else 0.0
