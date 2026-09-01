from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from drumscribe_ml.kit_adapter import (
    FEATURE_WIDTH,
    KitAdapterModel,
    candidate_vectors,
    dense_transient_frames,
    predict_features,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingError


def valid_model() -> KitAdapterModel:
    return KitAdapterModel(
        model_version="test",
        classes=TRAINING_CLASSES,
        thresholds=np.full(len(TRAINING_CLASSES), 0.5, dtype=np.float32),
        feature_mean=np.zeros(FEATURE_WIDTH, dtype=np.float32),
        feature_std=np.ones(FEATURE_WIDTH, dtype=np.float32),
        w1=np.zeros((4, FEATURE_WIDTH), dtype=np.float32),
        b1=np.zeros(4, dtype=np.float32),
        layer_norm_weight=np.ones(4, dtype=np.float32),
        layer_norm_bias=np.zeros(4, dtype=np.float32),
        w2=np.zeros((3, 4), dtype=np.float32),
        b2=np.zeros(3, dtype=np.float32),
        w3=np.zeros((len(TRAINING_CLASSES), 3), dtype=np.float32),
        b3=np.zeros(len(TRAINING_CLASSES), dtype=np.float32),
    )


def test_dense_transients_retain_fast_separated_attacks() -> None:
    features = np.zeros((80, 80), dtype=np.float32)
    features[10, 50:] = 8
    features[18, 50:] = 7
    features[40, 50:] = 9
    assert dense_transient_frames(features, flux_quantile=0.8) == [10, 18, 40]


def test_candidate_vectors_have_stable_runtime_shape() -> None:
    features = np.arange(60 * 80, dtype=np.float32).reshape(60, 80) / 1_000
    vectors = candidate_vectors(features, [1, 20, 59])
    assert vectors.shape == (3, FEATURE_WIDTH)
    assert np.isfinite(vectors).all()


def test_model_rejects_noncanonical_class_order() -> None:
    model = valid_model()
    invalid = KitAdapterModel(
        **{name: getattr(model, name) for name in model.__dataclass_fields__ if name != "classes"},
        classes=tuple(reversed(TRAINING_CLASSES)),
    )
    with pytest.raises(TrainingError, match="canonical class order"):
        invalid._validate()


def test_zero_weight_model_returns_half_probabilities() -> None:
    model = valid_model()
    model._validate()
    probabilities = model.probabilities(np.zeros((2, FEATURE_WIDTH), dtype=np.float32))
    assert probabilities.shape == (2, len(TRAINING_CLASSES))
    assert np.allclose(probabilities, 0.5)


def test_prediction_suppresses_nearby_duplicate_hits_per_class() -> None:
    features = np.zeros((50, 80), dtype=np.float32)
    features[10, 40:] = 8
    features[12, 40:] = 7
    features[30, 40:] = 9
    model = replace(
        valid_model(),
        thresholds=np.full(len(TRAINING_CLASSES), 0.49, dtype=np.float32),
        flux_quantile=0.2,
        peak_distance_frames=1,
        class_peak_distance_frames=np.full(len(TRAINING_CLASSES), 5, dtype=np.int32),
    )
    kick_frames = [
        item.frame for item in predict_features(features, model) if item.instrument.value == "KICK"
    ]
    assert kick_frames == [10, 30]
