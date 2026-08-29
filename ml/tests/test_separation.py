import numpy as np
import pytest

from drumscribe_ml.separation import evaluate_separation_payload, scale_invariant_sdr


def _payload():
    reference = np.sin(np.linspace(0, np.pi * 4, 200)).tolist()
    estimate = (np.asarray(reference) + 0.01 * np.cos(np.linspace(0, np.pi, 200))).tolist()
    return {
        "evidenceLevel": "synthetic_tooling_only",
        "tracks": [
            {
                "id": "generated-rock",
                "condition": "clean_studio_rock",
                "provider": "test",
                "modelVersion": "test",
                "referenceSamples": reference,
                "estimateSamples": estimate,
                "listening": {
                    "bleed": 4,
                    "cymbalEnergy": 4,
                    "kickPreservation": 5,
                    "snarePreservation": 5,
                    "tomPreservation": 4,
                    "transientIntegrity": 4,
                },
            }
        ],
    }


def test_separation_metrics_and_coverage_are_explicit():
    report = evaluate_separation_payload(_payload())
    assert report["meanSiSdrDb"] > 20
    assert report["evidenceLevel"] == "synthetic_tooling_only"
    assert "live_recording" in report["coverage"]["missing"]


def test_si_sdr_rejects_silence_and_shape_mismatch():
    with pytest.raises(ValueError, match="non-silent"):
        scale_invariant_sdr(np.zeros(4), np.ones(4))
    with pytest.raises(ValueError, match="equally sized"):
        scale_invariant_sdr(np.ones(4), np.ones(3))
