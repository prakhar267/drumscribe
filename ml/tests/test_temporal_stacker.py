from __future__ import annotations

import numpy as np
import pytest

from drumscribe_ml.temporal_stacker import (
    DEFAULT_SOURCE_ORDER,
    EventFusionRule,
    StackerDecoderRule,
    decode_stacker_probabilities,
    fuse_event_streams,
    temporal_context_features,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingError


def _sources(frames: int = 4) -> dict[str, np.ndarray]:
    return {
        name: np.full((frames, len(TRAINING_CLASSES)), 0.5, dtype=np.float32)
        for name in DEFAULT_SOURCE_ORDER
    }


def test_temporal_context_features_are_aligned_and_finite() -> None:
    sources = _sources()
    sources["stemEnsemble"][0, 0] = 0.8
    features = temporal_context_features(sources, offsets=(-1, 0, 1))
    assert features.shape == (4, 3 * 4 * len(TRAINING_CLASSES))
    assert np.isfinite(features).all()
    assert features[0, 0] == pytest.approx(features[0, len(TRAINING_CLASSES)])


def test_temporal_context_rejects_misaligned_sources() -> None:
    sources = _sources()
    sources["mixtureSpecialist"] = sources["mixtureSpecialist"][:-1]
    with pytest.raises(TrainingError, match="must align"):
        temporal_context_features(sources)


def test_decoder_applies_frozen_onset_shift() -> None:
    probabilities = np.zeros((8, len(TRAINING_CLASSES)), dtype=np.float32)
    probabilities[4, 0] = 0.9
    rules = {
        instrument.value: StackerDecoderRule(
            threshold=0.5,
            peak_distance_frames=1,
            onset_shift_frames=-2 if index == 0 else 0,
        )
        for index, instrument in enumerate(TRAINING_CLASSES)
    }
    decoded = decode_stacker_probabilities(probabilities, rules)
    assert decoded[TRAINING_CLASSES[0].value] == [2]


def test_event_fusion_supports_union_and_intersection() -> None:
    rules = {instrument.value: EventFusionRule(mode="base") for instrument in TRAINING_CLASSES}
    first = TRAINING_CLASSES[0].value
    second = TRAINING_CLASSES[1].value
    rules[first] = EventFusionRule(mode="union", radius_seconds=0.05)
    rules[second] = EventFusionRule(mode="intersection", radius_seconds=0.03)
    fused = fuse_event_streams(
        [(1.0, first), (2.0, second)],
        [(1.02, first), (1.5, first), (2.02, second)],
        rules,
    )
    assert fused == [(1.0, first), (1.5, first), (2.0, second)]
