#!/usr/bin/env python3
"""Calibrate a frozen supported-kit checkpoint decoder on selected development data."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.training import (
    TRAINING_CLASSES,
    TrainingConfig,
    _apply_family_competition,
    _load_training_record,
    _match_frames,
    _peak_distance_candidates,
    _peak_frames,
    _threshold_candidates,
    _training_device,
    build_model,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metrics(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    denominator = 2 * tp + fp + fn
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "f1": 2 * tp / denominator if denominator else 0.0,
    }


def calibrate(
    checkpoint: Path,
    prepared_dataset: Path,
    *,
    device: str,
    tolerance_frames: int,
    maximum_shift_frames: int,
    split: str,
    group_id: str | None,
    fixed_decoder: bool,
    tolerance_milliseconds: float | None,
    offset_resolution_milliseconds: float,
    maximum_offset_milliseconds: float,
) -> dict[str, Any]:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - requires the training extra
        raise RuntimeError("install the ML training extra to calibrate") from exc

    prepared = json.loads(prepared_dataset.read_text(encoding="utf-8"))
    records = [
        record for record in prepared.get("records", []) if record.get("split") == split
    ]
    if group_id is not None:
        records = [record for record in records if record.get("groupId") == group_id]
    if not records:
        raise ValueError("prepared dataset contains no matching calibration records")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    config = TrainingConfig(**state["configuration"])
    frozen_thresholds = dict(state.get("validationThresholds", {}))
    frozen_peak_distances = dict(state.get("validationPeakDistances", {}))
    class_names = {instrument.value for instrument in TRAINING_CLASSES}
    if fixed_decoder and (
        set(frozen_thresholds) != class_names
        or set(frozen_peak_distances) != class_names
    ):
        raise ValueError("checkpoint does not contain a complete frozen decoder")
    selected_device = _training_device(torch, device)
    first = np.load(records[0]["featurePath"], allow_pickle=False)
    model = build_model(
        config,
        mel_bands=int(first["features"].shape[1]),
        class_count=len(TRAINING_CLASSES),
    ).to(selected_device)
    model.load_state_dict(state["model"])
    model.eval()

    evaluated: list[tuple[np.ndarray, np.ndarray, float, dict[str, list[float]]]] = []
    with torch.no_grad():
        for record in records:
            features, targets, _ = _load_training_record(record)
            with np.load(record["featurePath"], allow_pickle=False) as feature_cache:
                frame_seconds = int(feature_cache["hop_length"]) / int(
                    feature_cache["sample_rate"]
                )
            annotation = json.loads(
                Path(record["annotationPath"]).read_text(encoding="utf-8")
            )
            onset_seconds = {name: [] for name in class_names}
            for event in annotation.get("events", []):
                if event.get("instrument") in onset_seconds:
                    onset_seconds[event["instrument"]].append(
                        float(event["onsetSeconds"])
                    )
            for values in onset_seconds.values():
                values.sort()
            logits, _ = model(torch.from_numpy(features)[None].to(selected_device))
            probabilities = _apply_family_competition(
                torch.sigmoid(logits)[0].cpu().numpy()
            )
            evaluated.append((probabilities, targets, frame_seconds, onset_seconds))

    thresholds: dict[str, float] = {}
    peak_distances: dict[str, int] = {}
    frame_shifts: dict[str, int] = {}
    onset_offsets: dict[str, float] = {}
    per_class: dict[str, dict[str, float | int]] = {}
    totals = {"tp": 0, "fp": 0, "fn": 0}
    use_subframe_offsets = tolerance_milliseconds is not None
    if use_subframe_offsets:
        step_count = round(maximum_offset_milliseconds / offset_resolution_milliseconds)
        offset_candidates = tuple(
            index * offset_resolution_milliseconds / 1000
            for index in range(-step_count, step_count + 1)
        )
        shift_candidates = (0,)
    else:
        offset_candidates = (0.0,)
        shift_candidates = range(-maximum_shift_frames, maximum_shift_frames + 1)
    for class_index, instrument in enumerate(TRAINING_CLASSES):
        best: tuple[float, float, float, int, int, tuple[int, int, int]] | None = None
        distance_candidates = (
            (int(frozen_peak_distances[instrument.value]),)
            if fixed_decoder
            else _peak_distance_candidates()
        )
        threshold_candidates = (
            (float(frozen_thresholds[instrument.value]),)
            if fixed_decoder
            else _threshold_candidates()
        )
        for peak_distance in distance_candidates:
            tracks = []
            for probabilities, targets, frame_seconds, onset_seconds in evaluated:
                references = (
                    onset_seconds[instrument.value]
                    if use_subframe_offsets
                    else np.flatnonzero(targets[:, class_index] > 0).tolist()
                )
                class_probabilities = probabilities[:, class_index]
                candidates = [
                    (
                        frame * frame_seconds if use_subframe_offsets else frame,
                        float(class_probabilities[frame]),
                    )
                    for frame in _peak_frames(
                        class_probabilities,
                        threshold=-float("inf"),
                        minimum_distance_frames=peak_distance,
                    )
                ]
                tracks.append((references, candidates))
            for threshold in threshold_candidates:
                for shift in shift_candidates:
                    for onset_offset in offset_candidates:
                        tp = fp = fn = 0
                        for references, candidates in tracks:
                            predictions = [
                                frame + shift + onset_offset
                                for frame, probability in candidates
                                if probability >= threshold
                                and frame + shift + onset_offset >= 0
                            ]
                            counts = _match_frames(
                                references,
                                predictions,
                                tolerance=(
                                    tolerance_milliseconds / 1000
                                    if use_subframe_offsets
                                    else tolerance_frames
                                ),
                            )
                            tp += counts[0]
                            fp += counts[1]
                            fn += counts[2]
                        score = float(_metrics(tp, fp, fn)["f1"])
                        candidate = (
                            score,
                            -abs(onset_offset),
                            -abs(float(threshold) - 0.5),
                            -abs(shift),
                            -peak_distance,
                        )
                        if best is None or candidate > best[:5]:
                            best = (*candidate, (tp, fp, fn))
                            thresholds[instrument.value] = float(threshold)
                            peak_distances[instrument.value] = int(peak_distance)
                            frame_shifts[instrument.value] = int(shift)
                            onset_offsets[instrument.value] = float(onset_offset)
        assert best is not None
        tp, fp, fn = best[5]
        per_class[instrument.value] = {
            **_metrics(tp, fp, fn),
            "threshold": thresholds[instrument.value],
            "peakDistanceFrames": peak_distances[instrument.value],
            "onsetShiftFrames": frame_shifts[instrument.value],
            "onsetOffsetSeconds": onset_offsets[instrument.value],
        }
        totals["tp"] += tp
        totals["fp"] += fp
        totals["fn"] += fn

    return {
        "schemaVersion": 1,
        "modelVersion": (
            f"{config.model_version}-demucs-shift-v1"
            if fixed_decoder
            else f"{config.model_version}-onset{tolerance_frames}-v1"
        ),
        "checkpointSha256": _sha256(checkpoint),
        "calibrationDatasetSha256": _sha256(prepared_dataset),
        "calibrationSplit": split,
        "calibrationGroupId": group_id,
        "fixedThresholdsAndPeakDistances": fixed_decoder,
        "recordCount": len(records),
        "toleranceFrames": tolerance_frames,
        "toleranceMilliseconds": tolerance_milliseconds,
        "maximumShiftFrames": maximum_shift_frames,
        "offsetResolutionMilliseconds": offset_resolution_milliseconds,
        "maximumOffsetMilliseconds": maximum_offset_milliseconds,
        "thresholds": thresholds,
        "peakDistances": peak_distances,
        "onsetShiftFrames": frame_shifts,
        "onsetOffsetSeconds": onset_offsets,
        "validationMicro": _metrics(**totals),
        "validationMacroF1": sum(float(row["f1"]) for row in per_class.values())
        / len(per_class),
        "perClass": per_class,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--prepared-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--tolerance-frames", type=int, default=2)
    parser.add_argument("--maximum-shift-frames", type=int, default=4)
    parser.add_argument("--tolerance-ms", type=float)
    parser.add_argument("--offset-resolution-ms", type=float, default=1.0)
    parser.add_argument("--maximum-offset-ms", type=float, default=40.0)
    parser.add_argument("--split", default="validation")
    parser.add_argument("--group-id")
    parser.add_argument("--fixed-decoder", action="store_true")
    args = parser.parse_args()
    if args.tolerance_frames < 0 or args.maximum_shift_frames < 0:
        raise ValueError("frame tolerances must be non-negative")
    if args.tolerance_ms is not None and args.tolerance_ms < 0:
        raise ValueError("millisecond tolerance must be non-negative")
    if args.offset_resolution_ms <= 0 or args.maximum_offset_ms < 0:
        raise ValueError("offset resolution must be positive and maximum non-negative")
    payload = calibrate(
        args.checkpoint.resolve(strict=True),
        args.prepared_dataset.resolve(strict=True),
        device=args.device,
        tolerance_frames=args.tolerance_frames,
        maximum_shift_frames=args.maximum_shift_frames,
        split=args.split,
        group_id=args.group_id,
        fixed_decoder=args.fixed_decoder,
        tolerance_milliseconds=args.tolerance_ms,
        offset_resolution_milliseconds=args.offset_resolution_ms,
        maximum_offset_milliseconds=args.maximum_offset_ms,
    )
    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"output": str(destination), **payload["validationMicro"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
