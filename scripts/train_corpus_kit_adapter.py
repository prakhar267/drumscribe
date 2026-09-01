#!/usr/bin/env python3
"""Train the production-legal kit adapter on the diverse licensed corpus.

The future evaluation group is excluded before annotations are loaded.  A
completed earlier benchmark may be supplied as development adaptation data,
but it is never reported as a held-out score.
"""

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
    write_manifest,
)
from drumscribe_ml.training import TRAINING_CLASSES
from train_kit_adapter import (
    SEED,
    TOLERANCE_FRAMES,
    _device,
    _export,
    _fit,
    _probabilities,
    _sha256,
    _thresholds,
)

CLASS_INDEX = {
    instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)
}


def _record_seed(record: dict[str, object]) -> int:
    digest = hashlib.sha256(str(record["trackId"]).encode()).digest()
    return int.from_bytes(digest[:8], "little")


def _labels_for_frames(
    annotation_path: Path,
    frames: list[int],
) -> np.ndarray:
    payload = json.loads(annotation_path.read_text(encoding="utf-8"))
    references: list[tuple[int, int]] = []
    for event in payload["events"]:
        class_index = CLASS_INDEX.get(str(event["instrument"]))
        if class_index is None:
            continue
        references.append(
            (
                round(float(event["onsetSeconds"]) * SAMPLE_RATE / HOP_LENGTH),
                class_index,
            )
        )
    labels = np.zeros((len(frames), len(TRAINING_CLASSES)), dtype=np.float32)
    # Expand each reference across the accepted frame tolerance, then perform
    # constant-time lookups for every candidate.
    expanded: dict[int, set[int]] = {}
    for reference_frame, class_index in references:
        for frame in range(
            reference_frame - TOLERANCE_FRAMES,
            reference_frame + TOLERANCE_FRAMES + 1,
        ):
            expanded.setdefault(frame, set()).add(class_index)
    for row, frame in enumerate(frames):
        for class_index in expanded.get(frame, ()):
            labels[row, class_index] = 1
    return labels


def _sample_candidates(
    frames: list[int],
    labels: np.ndarray,
    *,
    maximum_positive: int,
    maximum_negative: int,
    seed: int,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    positive = np.flatnonzero(labels.any(axis=1))
    negative = np.flatnonzero(~labels.any(axis=1))
    if len(positive) > maximum_positive:
        # Keep rare-class examples first, then sample the remaining slots.
        class_frequency = np.maximum(labels[positive].sum(axis=0), 1)
        rarity = (labels[positive] / class_frequency).sum(axis=1)
        required_count = max(1, maximum_positive // 3)
        required = positive[np.argsort(-rarity, kind="stable")[:required_count]]
        remaining = np.setdiff1d(positive, required, assume_unique=False)
        sampled = rng.choice(
            remaining,
            size=maximum_positive - len(required),
            replace=False,
        )
        positive = np.concatenate((required, sampled))
    if len(negative) > maximum_negative:
        negative = rng.choice(negative, size=maximum_negative, replace=False)
    selected = np.sort(np.concatenate((positive, negative)))
    return selected.astype(np.int32)


def _load_records(
    records: list[dict[str, object]],
    *,
    flux_quantile: float,
    peak_distance_frames: int,
    maximum_positive: int,
    maximum_negative: int,
    progress_label: str,
) -> tuple[np.ndarray, np.ndarray]:
    vector_chunks: list[np.ndarray] = []
    label_chunks: list[np.ndarray] = []
    for index, record in enumerate(records, start=1):
        with np.load(Path(str(record["featurePath"])), allow_pickle=False) as arrays:
            features = np.asarray(arrays["features"], dtype=np.float32)
        frames = dense_transient_frames(
            features,
            flux_quantile=flux_quantile,
            minimum_distance_frames=peak_distance_frames,
        )
        labels = _labels_for_frames(Path(str(record["annotationPath"])), frames)
        selected = _sample_candidates(
            frames,
            labels,
            maximum_positive=maximum_positive,
            maximum_negative=maximum_negative,
            seed=_record_seed(record),
        )
        vector_chunks.append(candidate_vectors(features, [frames[i] for i in selected]))
        label_chunks.append(labels[selected])
        if index % 100 == 0 or index == len(records):
            print(f"{progress_label}: {index}/{len(records)} records", flush=True)
    return (
        np.concatenate(vector_chunks).astype(np.float32),
        np.concatenate(label_chunks).astype(np.float32),
    )


def _load_development_adaptation(
    benchmark: Path,
    *,
    flux_quantile: float,
    peak_distance_frames: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, Path]:
    result_path = benchmark / "benchmark-result.json"
    annotation_path = benchmark / "reference-events.json"
    feature_path = benchmark / "prediction" / "drum-stem-features.npz"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("benchmark") not in {
        "sealed-original-metal-v1",
        "excluded-groove-metal-v2",
    }:
        raise ValueError("unsupported completed development benchmark")
    if result.get("testProtocol", {}).get("postTestTuning") is not False:
        raise ValueError("development adaptation is not a completed untouched run")
    with np.load(feature_path, allow_pickle=False) as arrays:
        features = np.asarray(arrays["features"], dtype=np.float32)
    frames = dense_transient_frames(
        features,
        flux_quantile=flux_quantile,
        minimum_distance_frames=peak_distance_frames,
    )
    labels = _labels_for_frames(annotation_path, frames)
    calibration_mask = np.asarray([int(frame) % 5 == 0 for frame in frames], dtype=bool)
    training_indices = np.flatnonzero(~calibration_mask)
    calibration_indices = np.flatnonzero(calibration_mask)
    training_vectors = []
    training_labels = []
    for shift in (-2, -1, 0, 1, 2):
        training_vectors.append(
            candidate_vectors(
                features,
                [frames[index] + shift for index in training_indices],
            )
        )
        training_labels.append(labels[training_indices])
    return (
        np.concatenate(training_vectors).astype(np.float32),
        np.concatenate(training_labels).astype(np.float32),
        candidate_vectors(features, [frames[index] for index in calibration_indices]),
        labels[calibration_indices].astype(np.float32),
        annotation_path,
    )


def _micro_f1(
    probabilities: np.ndarray, labels: np.ndarray, thresholds: np.ndarray
) -> float:
    predicted = probabilities >= thresholds
    truth = labels > 0
    true_positive = int(np.sum(predicted & truth))
    false_positive = int(np.sum(predicted & ~truth))
    false_negative = int(np.sum(~predicted & truth))
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else 0.0


def _reference_frames_by_class(path: Path) -> list[list[int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rawHits", payload.get("events", []))
    references: list[list[int]] = [[] for _ in TRAINING_CLASSES]
    for event in rows:
        class_index = CLASS_INDEX.get(str(event["instrument"]))
        if class_index is not None:
            references[class_index].append(
                round(float(event["onsetSeconds"]) * SAMPLE_RATE / HOP_LENGTH)
            )
    return [sorted(values) for values in references]


def _match_frame_counts(
    reference: list[int], prediction: list[int], tolerance: int
) -> tuple[int, int, int]:
    reference_index = prediction_index = true_positive = 0
    while reference_index < len(reference) and prediction_index < len(prediction):
        delta = prediction[prediction_index] - reference[reference_index]
        if delta < -tolerance:
            prediction_index += 1
        elif delta > tolerance:
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


def _calibration_record(
    torch,
    model,
    *,
    feature_path: Path,
    reference_path: Path,
    mean: np.ndarray,
    std: np.ndarray,
    device: str,
    flux_quantile: float,
    peak_distance_frames: int,
) -> tuple[list[int], np.ndarray, list[list[int]]]:
    with np.load(feature_path, allow_pickle=False) as arrays:
        features = np.asarray(arrays["features"], dtype=np.float32)
    frames = dense_transient_frames(
        features,
        flux_quantile=flux_quantile,
        minimum_distance_frames=peak_distance_frames,
    )
    vectors = candidate_vectors(features, frames)
    vectors = ((vectors - mean) / std).astype(np.float32)
    probabilities = _probabilities(torch, model, vectors, device)
    return frames, probabilities, _reference_frames_by_class(reference_path)


def _event_level_calibration(
    torch,
    model,
    *,
    validation_records: list[dict[str, object]],
    development_benchmarks: list[Path],
    mean: np.ndarray,
    std: np.ndarray,
    device: str,
    flux_quantile: float,
    peak_distance_frames: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    records = [
        _calibration_record(
            torch,
            model,
            feature_path=Path(str(record["featurePath"])),
            reference_path=Path(str(record["annotationPath"])),
            mean=mean,
            std=std,
            device=device,
            flux_quantile=flux_quantile,
            peak_distance_frames=peak_distance_frames,
        )
        for record in validation_records
    ]
    for benchmark in development_benchmarks:
        records.append(
            _calibration_record(
                torch,
                model,
                feature_path=benchmark / "prediction" / "drum-stem-features.npz",
                reference_path=benchmark / "reference-events.json",
                mean=mean,
                std=std,
                device=device,
                flux_quantile=flux_quantile,
                peak_distance_frames=peak_distance_frames,
            )
        )
    thresholds: list[float] = []
    distances: list[int] = []
    totals = [0, 0, 0]
    for class_index in range(len(TRAINING_CLASSES)):
        best: tuple[float, float, int, tuple[int, int, int]] | None = None
        for distance in range(1, 16):
            # Score-ordered greedy NMS can run once per distance. Applying a
            # threshold afterward is equivalent to rerunning NMS on that prefix.
            suppressed_records: list[
                tuple[np.ndarray, np.ndarray, list[int]]
            ] = []
            for frames, probabilities, references in records:
                ordered = np.argsort(-probabilities[:, class_index])
                kept: list[int] = []
                occupied = np.zeros(
                    (max(frames) + distance + 1) if frames else 0, dtype=bool
                )
                for row in ordered:
                    frame = frames[int(row)]
                    start = max(0, frame - distance + 1)
                    end = min(len(occupied), frame + distance)
                    if not occupied[start:end].any():
                        kept.append(int(row))
                        occupied[frame] = True
                suppressed_records.append(
                    (
                        np.asarray([frames[row] for row in kept], dtype=np.int32),
                        probabilities[kept, class_index],
                        references[class_index],
                    )
                )
            for threshold in np.linspace(0.05, 0.995, 64):
                aggregate = [0, 0, 0]
                for kept_frames, kept_scores, references in suppressed_records:
                    counts = _match_frame_counts(
                        references,
                        sorted(kept_frames[kept_scores >= threshold].tolist()),
                        TOLERANCE_FRAMES,
                    )
                    for index, value in enumerate(counts):
                        aggregate[index] += value
                true_positive, false_positive, false_negative = aggregate
                denominator = 2 * true_positive + false_positive + false_negative
                f1 = 2 * true_positive / denominator if denominator else 0.0
                candidate = (f1, float(threshold), distance, tuple(aggregate))
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
        assert best is not None
        thresholds.append(best[1])
        distances.append(best[2])
        for index, value in enumerate(best[3]):
            totals[index] += value
    true_positive, false_positive, false_negative = totals
    denominator = 2 * true_positive + false_positive + false_negative
    micro_f1 = 2 * true_positive / denominator if denominator else 0.0
    return (
        np.asarray(thresholds, dtype=np.float32),
        np.asarray(distances, dtype=np.int32),
        micro_f1,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-dataset", type=Path, required=True)
    parser.add_argument("--development-benchmark", type=Path, required=True)
    parser.add_argument(
        "--additional-development-benchmark", type=Path, action="append", default=[]
    )
    parser.add_argument("--excluded-group", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-version", default="kit-adaptive-corpus-v18")
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    parser.add_argument("--steps", type=int, default=3_200)
    parser.add_argument("--flux-quantile", type=float, default=0.30)
    parser.add_argument("--peak-distance-frames", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists() or args.manifest.exists():
        raise FileExistsError("model output and manifest must be new files")
    try:
        import torch
    except ImportError as exc:
        raise SystemExit("training requires PyTorch") from exc

    prepared_path = args.prepared_dataset.resolve(strict=True)
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    original = [
        record for record in payload["records"] if record["variant"] == "original"
    ]
    excluded = [
        record for record in original if record["groupId"] == args.excluded_group
    ]
    if not excluded:
        raise ValueError(f"excluded group is absent: {args.excluded_group}")
    training_records = [
        record
        for record in original
        if record["split"] == "train" and record["groupId"] != args.excluded_group
    ]
    validation_records = [
        record for record in original if record["split"] == "validation"
    ]

    training_vectors, training_labels = _load_records(
        training_records,
        flux_quantile=args.flux_quantile,
        peak_distance_frames=args.peak_distance_frames,
        maximum_positive=65,
        maximum_negative=22,
        progress_label="training corpus",
    )
    validation_vectors, validation_labels = _load_records(
        validation_records,
        flux_quantile=args.flux_quantile,
        peak_distance_frames=args.peak_distance_frames,
        maximum_positive=180,
        maximum_negative=80,
        progress_label="validation corpus",
    )
    adaptation_sets = [
        _load_development_adaptation(
            benchmark.resolve(strict=True),
            flux_quantile=args.flux_quantile,
            peak_distance_frames=args.peak_distance_frames,
        )
        for benchmark in (
            args.development_benchmark,
            *args.additional_development_benchmark,
        )
    ]
    adaptation_vectors = np.concatenate([item[0] for item in adaptation_sets])
    adaptation_labels = np.concatenate([item[1] for item in adaptation_sets])
    adaptation_calibration_vectors = np.concatenate(
        [item[2] for item in adaptation_sets]
    )
    adaptation_calibration_labels = np.concatenate(
        [item[3] for item in adaptation_sets]
    )
    adaptation_references = [item[4] for item in adaptation_sets]
    # Modest repetition supplies metal/isolated-stem domain adaptation without
    # allowing one kit to dominate the varied corpus.
    training_vectors = np.concatenate(
        (training_vectors, np.tile(adaptation_vectors, (3, 1)))
    ).astype(np.float32)
    training_labels = np.concatenate(
        (training_labels, np.tile(adaptation_labels, (3, 1)))
    ).astype(np.float32)

    mean = training_vectors.mean(axis=0).astype(np.float32)
    std = (training_vectors.std(axis=0) + 1e-4).astype(np.float32)
    training_vectors = ((training_vectors - mean) / std).astype(np.float32)
    calibration_vectors = np.concatenate(
        (validation_vectors, adaptation_calibration_vectors)
    ).astype(np.float32)
    calibration_labels = np.concatenate(
        (validation_labels, adaptation_calibration_labels)
    ).astype(np.float32)
    calibration_vectors = ((calibration_vectors - mean) / std).astype(np.float32)

    device = _device(torch, args.device)
    indices = np.arange(len(training_vectors))
    model = _fit(
        torch,
        training_vectors,
        training_labels,
        indices,
        device=device,
        steps=args.steps,
        seed=SEED + 100,
    )
    probabilities = _probabilities(torch, model, calibration_vectors, device)
    candidate_thresholds = _thresholds(probabilities, calibration_labels)
    development_benchmarks = [
        benchmark.resolve(strict=True)
        for benchmark in (
            args.development_benchmark,
            *args.additional_development_benchmark,
        )
    ]
    thresholds, class_peak_distances, event_calibration_f1 = _event_level_calibration(
        torch,
        model,
        validation_records=validation_records,
        development_benchmarks=development_benchmarks,
        mean=mean,
        std=std,
        device=device,
        flux_quantile=args.flux_quantile,
        peak_distance_frames=args.peak_distance_frames,
    )
    provenance_hash = hashlib.sha256(
        (
            _sha256(prepared_path)
            + "".join(_sha256(path) for path in adaptation_references)
        ).encode()
    ).hexdigest()
    _export(
        torch,
        model,
        args.output,
        mean=mean,
        std=std,
        thresholds=thresholds,
        model_version=args.model_version,
        reference_sha256=provenance_hash,
        flux_quantile=args.flux_quantile,
        peak_distance_frames=args.peak_distance_frames,
        class_peak_distance_frames=class_peak_distances,
    )
    serving_model = KitAdapterModel.load(args.output)
    serving_probabilities = serving_model.probabilities(
        calibration_vectors * std + mean
    )
    write_manifest(args.output, args.manifest)
    print(
        json.dumps(
            {
                "model": str(args.output.resolve()),
                "manifest": str(args.manifest.resolve()),
                "modelVersion": args.model_version,
                "device": device,
                "excludedGroup": args.excluded_group,
                "excludedTracks": [record["trackId"] for record in excluded],
                "trainingRecords": len(training_records),
                "trainingExamples": len(training_vectors),
                "calibrationExamples": len(calibration_vectors),
                "calibrationCandidateMicroF1": _micro_f1(
                    serving_probabilities,
                    calibration_labels,
                    candidate_thresholds,
                ),
                "calibrationEventMicroF1At50ms": event_calibration_f1,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
