import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from drumscribe_ml.multiview import (
    MultiViewConfig,
    MultiViewRule,
    blend_multiview_probabilities,
    decode_multiview_probabilities,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingError


def _rules() -> dict[str, MultiViewRule]:
    return {
        instrument.value: MultiViewRule(
            model_weights={"stem": 0.75, "mixture": 0.25},
            threshold=0.6,
            peak_distance_frames=2,
        )
        for instrument in TRAINING_CLASSES
    }


def test_multiview_blends_each_class_with_fixed_weights() -> None:
    stem = np.full((4, len(TRAINING_CLASSES)), 0.8, dtype=np.float32)
    mixture = np.full((4, len(TRAINING_CLASSES)), 0.4, dtype=np.float32)

    actual = blend_multiview_probabilities({"stem": stem, "mixture": mixture}, _rules())

    assert actual.shape == stem.shape
    assert np.allclose(actual, 0.7)


def test_multiview_decoder_returns_fused_confidence_and_peaks() -> None:
    stem = np.zeros((6, len(TRAINING_CLASSES)), dtype=np.float32)
    mixture = np.zeros_like(stem)
    stem[2, 0] = 1.0
    mixture[2, 0] = 0.6

    probabilities, decoded = decode_multiview_probabilities(
        {"stem": stem, "mixture": mixture}, _rules()
    )

    assert probabilities[2, 0] == pytest.approx(0.9)
    assert decoded[TRAINING_CLASSES[0].value] == [2]


def test_multiview_rejects_missing_or_misaligned_sources() -> None:
    probabilities = np.zeros((3, len(TRAINING_CLASSES)), dtype=np.float32)
    with pytest.raises(TrainingError, match="missing multi-view"):
        blend_multiview_probabilities({"stem": probabilities}, _rules())
    with pytest.raises(TrainingError, match="identical shapes"):
        blend_multiview_probabilities(
            {"stem": probabilities, "mixture": probabilities[:2]}, _rules()
        )


def test_frozen_v19_config_is_explicitly_development_only() -> None:
    repository = Path(__file__).resolve().parents[2]
    path = repository / "ml/configs/groove-multiview-articulation-v19.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    config = MultiViewConfig.load(path)

    assert config.model_version == "groove-multiview-articulation-v19-development"
    assert config.production_approved is False
    assert payload["calibration"]["corpusLicense"] == "CC BY-NC 4.0"
    assert set(config.rules) == {instrument.value for instrument in TRAINING_CLASSES}

    ensemble = repository / payload["components"]["stackedEnsemble"]["config"]
    specialist = repository / payload["components"]["focalSpecialist"]["checkpoint"]
    assert (
        hashlib.sha256(ensemble.read_bytes()).hexdigest()
        == payload["components"]["stackedEnsemble"]["sha256"]
    )
    assert (
        hashlib.sha256(specialist.read_bytes()).hexdigest()
        == payload["components"]["focalSpecialist"]["sha256"]
    )
