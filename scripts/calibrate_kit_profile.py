#!/usr/bin/env python3
"""Freeze a drum-kit-specific decoder from an already unsealed benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from drumscribe_ml.kit_adapter import (
    HOP_LENGTH,
    SAMPLE_RATE,
    KitAdapterModel,
    candidate_vectors,
    dense_transient_frames,
    model_manifest,
)
from drumscribe_ml.training import TRAINING_CLASSES

TOLERANCE_SECONDS = 0.050


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _match(reference: list[float], prediction: list[float]) -> tuple[int, int, int]:
    reference_index = prediction_index = true_positive = 0
    while reference_index < len(reference) and prediction_index < len(prediction):
        delta = prediction[prediction_index] - reference[reference_index]
        if delta < -TOLERANCE_SECONDS:
            prediction_index += 1
        elif delta > TOLERANCE_SECONDS:
            reference_index += 1
        else:
            true_positive += 1
            reference_index += 1
            prediction_index += 1
    return (
        true_positive,
        len(prediction) - true_positive,
        len(reference) - true_positive,
    )


def _nms_rows(
    probabilities: np.ndarray,
    frames: list[int],
    *,
    class_index: int,
    distance: int,
) -> list[int]:
    ordered = np.argsort(-probabilities[:, class_index])
    occupied = np.zeros(max(frames) + distance + 1, dtype=bool)
    kept: list[int] = []
    for row in ordered:
        frame = frames[int(row)]
        if not occupied[max(0, frame - distance + 1) : frame + distance].any():
            kept.append(int(row))
            occupied[frame] = True
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True)
    parser.add_argument("--development-benchmark", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--profile-scope", required=True)
    args = parser.parse_args()
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("profile output and manifest must be new")

    benchmark = args.development_benchmark.resolve(strict=True)
    result = json.loads((benchmark / "benchmark-result.json").read_text())
    if result.get("benchmark") != "sealed-original-metal-v1":
        raise ValueError(
            "profile calibration requires the completed v1 development song"
        )
    if result.get("testProtocol", {}).get("postTestTuning") is not False:
        raise ValueError("development benchmark protocol is not frozen")
    reference_path = benchmark / "reference-events.json"
    feature_path = benchmark / "prediction" / "drum-stem-features.npz"
    base_path = args.base_model.resolve(strict=True)
    base = KitAdapterModel.load(base_path)
    with np.load(feature_path, allow_pickle=False) as arrays:
        features = np.asarray(arrays["features"], dtype=np.float32)
    frames = dense_transient_frames(
        features,
        flux_quantile=base.flux_quantile,
        minimum_distance_frames=base.peak_distance_frames,
    )
    probabilities = base.probabilities(candidate_vectors(features, frames))
    reference_payload = json.loads(reference_path.read_text())
    references = {
        instrument.value: sorted(
            float(event["onsetSeconds"])
            for event in reference_payload["events"]
            if event["instrument"] == instrument.value
        )
        for instrument in TRAINING_CLASSES
    }

    thresholds: list[float] = []
    distances: list[int] = []
    per_class: dict[str, dict[str, float | int]] = {}
    totals = [0, 0, 0]
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        best: tuple[float, float, int, tuple[int, int, int]] | None = None
        for distance in range(1, 16):
            kept = _nms_rows(
                probabilities,
                frames,
                class_index=class_index,
                distance=distance,
            )
            for threshold in np.linspace(0.05, 0.995, 190):
                predicted = sorted(
                    frames[row] * HOP_LENGTH / SAMPLE_RATE
                    for row in kept
                    if probabilities[row, class_index] >= threshold
                )
                counts = _match(references[instrument.value], predicted)
                true_positive, false_positive, false_negative = counts
                denominator = 2 * true_positive + false_positive + false_negative
                f1 = 2 * true_positive / denominator if denominator else 0.0
                candidate = (f1, float(threshold), distance, counts)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
        assert best is not None
        thresholds.append(best[1])
        distances.append(best[2])
        true_positive, false_positive, false_negative = best[3]
        for index, value in enumerate(best[3]):
            totals[index] += value
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / max(1, true_positive + false_negative)
        per_class[instrument.value] = {
            "threshold": best[1],
            "peakDistanceFrames": best[2],
            "precision": precision,
            "recall": recall,
            "f1": best[0],
        }

    with np.load(base_path, allow_pickle=False) as arrays:
        payload = {name: np.asarray(arrays[name]) for name in arrays.files}
    payload.update(
        {
            "model_version": np.array(args.model_version),
            "thresholds": np.asarray(thresholds, dtype=np.float32),
            "class_peak_distance_frames": np.asarray(distances, dtype=np.int32),
            "profile_scope": np.array(args.profile_scope),
            "base_model_sha256": np.array(_sha256(base_path)),
            "calibration_reference_sha256": np.array(_sha256(reference_path)),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **payload)
    KitAdapterModel.load(args.output)
    true_positive, false_positive, false_negative = totals
    denominator = 2 * true_positive + false_positive + false_negative
    development_f1 = 2 * true_positive / denominator if denominator else 0.0
    manifest = model_manifest(args.output)
    manifest.update(
        {
            "profileScope": args.profile_scope,
            "baseModelSha256": _sha256(base_path),
            "calibrationReferenceSha256": _sha256(reference_path),
            "developmentEventF1At50ms": development_f1,
            "developmentPerClass": per_class,
            "testStatus": "not_evaluated",
        }
    )
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "model": str(args.output.resolve()),
                "manifest": str(args.manifest.resolve()),
                "developmentEventF1At50ms": development_f1,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
