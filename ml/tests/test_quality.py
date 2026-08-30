import math
from copy import deepcopy

from drumscribe_music import Instrument

from drumscribe_ml.quality import AccuracyThresholds, evaluate_accuracy_gate


def _passing_evidence():
    metrics = {
        "tp": 1_000,
        "fp": 0,
        "fn": 0,
        "support": 1_000,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "timingMaeSeconds": 0.001,
        "macroF1": 1.0,
        "meanPerSongF1": 1.0,
    }
    report = {
        "evidenceLevel": "licensed_held_out_evaluation",
        "songCount": 120,
        "durationSeconds": 40_000,
        "onsetToleranceReports": {
            "25": {
                "overall": metrics,
                "classes": {instrument.value: metrics for instrument in Instrument},
                "conditions": {"clean_stem": metrics, "full_mix": metrics},
            }
        },
    }
    evidence = {
        "beatF1At50ms": 1.0,
        "downbeatF1At50ms": 1.0,
        "notationClassAndSlotF1": 1.0,
        "notationSlotF1": 1.0,
        "tempoAccuracy": 1.0,
        "velocityAccuracy": 1.0,
        "separationCorrelation": 1.0,
        "separationSiSdrDb": 30.0,
        "exportPassRate": 1.0,
        "browserPassRate": 1.0,
    }
    return report, evidence


def test_accuracy_gate_passes_only_complete_held_out_evidence():
    report, evidence = _passing_evidence()
    result = evaluate_accuracy_gate(report, evidence)
    assert result.passed
    assert not result.failures


def test_accuracy_gate_fails_missing_classes_and_sub_target_metrics():
    report, evidence = _passing_evidence()
    failing = deepcopy(report)
    failing["onsetToleranceReports"]["25"]["classes"].pop("TAMBOURINE")
    evidence["notationClassAndSlotF1"] = 0.989
    result = evaluate_accuracy_gate(
        failing,
        evidence,
        thresholds=AccuracyThresholds(minimum_hours=1),
    )
    assert not result.passed
    assert any("TAMBOURINE.support" in failure for failure in result.failures)
    assert any("notationClassAndSlotF1" in failure for failure in result.failures)


def test_accuracy_gate_rejects_non_finite_and_boolean_metrics():
    report, evidence = _passing_evidence()
    report["songCount"] = True
    report["onsetToleranceReports"]["25"]["overall"]["f1"] = math.nan
    evidence["beatF1At50ms"] = math.inf
    result = evaluate_accuracy_gate(report, evidence)
    assert not result.passed
    assert any("songCount" in failure for failure in result.failures)
    assert any("onset25ms.overall.f1" in failure for failure in result.failures)
    assert any("beatF1At50ms" in failure for failure in result.failures)
