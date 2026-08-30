"""Fail-closed release gate for DrumScribe's measured accuracy target."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from drumscribe_music import Instrument


@dataclass(frozen=True, slots=True)
class AccuracyThresholds:
    minimum_score: float = 0.99
    minimum_songs: int = 100
    minimum_hours: float = 10.0
    minimum_class_support: int = 100
    maximum_timing_mae_seconds: float = 0.01
    minimum_separation_correlation: float = 0.99
    minimum_separation_si_sdr_db: float = 20.0


@dataclass(frozen=True, slots=True)
class QualityGateResult:
    passed: bool
    failures: tuple[str, ...]
    thresholds: dict[str, Any]


DEFAULT_ACCURACY_THRESHOLDS = AccuracyThresholds()


def evaluate_accuracy_gate(
    benchmark: dict[str, Any],
    evidence: dict[str, Any],
    *,
    thresholds: AccuracyThresholds = DEFAULT_ACCURACY_THRESHOLDS,
) -> QualityGateResult:
    """Require broad held-out evidence; missing metrics fail instead of being ignored."""

    failures: list[str] = []

    def require_at_least(path: str, value: Any, minimum: float) -> None:
        if not _finite_number(value) or float(value) < minimum:
            failures.append(f"{path} must be >= {minimum:g}; measured {value!r}")

    def require_at_most(path: str, value: Any, maximum: float) -> None:
        if not _finite_number(value) or float(value) > maximum:
            failures.append(f"{path} must be <= {maximum:g}; measured {value!r}")

    if benchmark.get("evidenceLevel") != "licensed_held_out_evaluation":
        failures.append("evidenceLevel must be 'licensed_held_out_evaluation'")
    require_at_least("songCount", benchmark.get("songCount"), thresholds.minimum_songs)
    require_at_least(
        "durationHours",
        _number(benchmark.get("durationSeconds")) / 3600,
        thresholds.minimum_hours,
    )

    tolerance_report = benchmark.get("onsetToleranceReports", {}).get("25", {})
    overall = tolerance_report.get("overall", {})
    for metric in ("precision", "recall", "f1", "macroF1", "meanPerSongF1"):
        require_at_least(
            f"onset25ms.overall.{metric}", overall.get(metric), thresholds.minimum_score
        )
    require_at_most(
        "onset25ms.overall.timingMaeSeconds",
        overall.get("timingMaeSeconds"),
        thresholds.maximum_timing_mae_seconds,
    )

    classes = tolerance_report.get("classes", {})
    for instrument in Instrument:
        metrics = classes.get(instrument.value, {})
        require_at_least(
            f"classes.{instrument.value}.support",
            metrics.get("support"),
            thresholds.minimum_class_support,
        )
        for metric in ("precision", "recall", "f1"):
            require_at_least(
                f"classes.{instrument.value}.{metric}",
                metrics.get(metric),
                thresholds.minimum_score,
            )

    conditions = tolerance_report.get("conditions", {})
    for condition in ("clean_stem", "full_mix"):
        metrics = conditions.get(condition, {})
        for metric in ("precision", "recall", "f1"):
            require_at_least(
                f"conditions.{condition}.{metric}",
                metrics.get(metric),
                thresholds.minimum_score,
            )

    for metric in (
        "beatF1At50ms",
        "downbeatF1At50ms",
        "notationClassAndSlotF1",
        "notationSlotF1",
        "tempoAccuracy",
        "velocityAccuracy",
    ):
        require_at_least(f"evidence.{metric}", evidence.get(metric), thresholds.minimum_score)
    require_at_least(
        "evidence.separationCorrelation",
        evidence.get("separationCorrelation"),
        thresholds.minimum_separation_correlation,
    )
    require_at_least(
        "evidence.separationSiSdrDb",
        evidence.get("separationSiSdrDb"),
        thresholds.minimum_separation_si_sdr_db,
    )
    for metric in ("exportPassRate", "browserPassRate"):
        require_at_least(f"evidence.{metric}", evidence.get(metric), 1.0)

    return QualityGateResult(not failures, tuple(failures), asdict(thresholds))


def _number(value: Any) -> float:
    return float(value) if _finite_number(value) else float("-inf")


def _finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
