#!/usr/bin/env python3
"""Calibrate ADTOF decoding on MDB Drums without touching the test labels.

MDB is used as research-only evaluation data. Decoder parameters are selected
solely from the official MIREX training split and frozen for both splits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from adtof_pytorch import (
    LABELS_5,
    activations_to_pretty_midi,
    calculate_n_bins,
    create_frame_rnn_model,
    load_audio_for_model,
    load_pytorch_weights,
)
from adtof_pytorch.post_processing import NotePeakPickingProcessor

TRAIN_TRACKS = (
    "MusicDelta_80sRock",
    "MusicDelta_BebopJazz",
    "MusicDelta_Britpop",
    "MusicDelta_CoolJazz",
    "MusicDelta_Disco",
    "MusicDelta_FunkJazz",
    "MusicDelta_FusionJazz",
    "MusicDelta_Reggae",
    "MusicDelta_Rock",
    "MusicDelta_Rockabilly",
    "MusicDelta_Shadows",
    "MusicDelta_Zeppelin",
)
TEST_TRACKS = (
    "MusicDelta_Beatles",
    "MusicDelta_Country1",
    "MusicDelta_FreeJazz",
    "MusicDelta_Gospel",
    "MusicDelta_Grunge",
    "MusicDelta_Hendrix",
    "MusicDelta_LatinJazz",
    "MusicDelta_ModalJazz",
    "MusicDelta_Punk",
    "MusicDelta_SpeedMetal",
    "MusicDelta_SwingJazz",
)
MIDI_TO_MDB = {35: "KD", 38: "SD", 47: "TT", 42: "HH", 49: "CY"}
DEFAULT_THRESHOLDS = {35: 0.22, 38: 0.24, 47: 0.32, 42: 0.22, 49: 0.30}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_times(
    path: Path, label: str, *, max_seconds: float | None = None
) -> list[float]:
    return sorted(
        float(parts[0])
        for line in path.read_text(encoding="utf-8").splitlines()
        if len(parts := line.split()) >= 2
        and parts[1] == label
        and (max_seconds is None or float(parts[0]) < max_seconds)
    )


def _counts(
    references: list[float], predictions: list[float], tolerance: float
) -> tuple[int, int, int]:
    reference_index = prediction_index = true_positive = 0
    false_positive = false_negative = 0
    while reference_index < len(references) and prediction_index < len(predictions):
        reference = references[reference_index]
        prediction = predictions[prediction_index]
        if prediction < reference - tolerance:
            false_positive += 1
            prediction_index += 1
        elif reference < prediction - tolerance:
            false_negative += 1
            reference_index += 1
        else:
            true_positive += 1
            reference_index += 1
            prediction_index += 1
    false_positive += len(predictions) - prediction_index
    false_negative += len(references) - reference_index
    return true_positive, false_positive, false_negative


def _f1(counts: tuple[int, int, int]) -> float:
    true_positive, false_positive, false_negative = counts
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else 0.0


def _load_or_create_activations(
    *,
    tracks: tuple[str, ...],
    audio_root: Path,
    audio_suffix: str,
    cache_root: Path,
    model: Any,
    device: str,
) -> dict[str, np.ndarray]:
    import torch

    cache_root.mkdir(parents=True, exist_ok=True)
    activations: dict[str, np.ndarray] = {}
    for track in tracks:
        audio_path = audio_root / f"{track}{audio_suffix}"
        cache_path = cache_root / f"{track}.npy"
        if cache_path.exists():
            activation = np.load(cache_path, allow_pickle=False)
        else:
            model_input = load_audio_for_model(str(audio_path)).to(device)
            with torch.no_grad():
                activation = model(model_input).cpu().numpy()[0]
            temporary = cache_path.with_suffix(".tmp.npy")
            np.save(temporary, activation.astype(np.float32, copy=False))
            temporary.replace(cache_path)
        if activation.ndim != 2 or activation.shape[1] != len(LABELS_5):
            raise RuntimeError(
                f"unexpected activation shape for {track}: {activation.shape}"
            )
        activations[track] = activation
        print(json.dumps({"cached": track, "shape": activation.shape}), flush=True)
    return activations


def _pick(
    activation: np.ndarray,
    class_index: int,
    *,
    threshold: float,
    pre_average: float,
    pre_maximum: float,
    combine: float,
    offset: float,
) -> list[float]:
    processor = NotePeakPickingProcessor(
        threshold=threshold,
        pre_avg=pre_average,
        post_avg=0.01,
        pre_max=pre_maximum,
        post_max=0.01,
        combine=combine,
        fps=100,
    )
    return [
        max(0.0, time + offset)
        for time, _ in processor.process(activation[:, class_index])
    ]


def _aggregate_class_score(
    *,
    tracks: tuple[str, ...],
    activations: dict[str, np.ndarray],
    references: dict[tuple[str, int], list[float]],
    class_index: int,
    parameters: dict[str, float],
    tolerance: float,
) -> tuple[float, tuple[int, int, int]]:
    totals = [0, 0, 0]
    for track in tracks:
        predictions = _pick(
            activations[track],
            class_index,
            threshold=parameters["threshold"],
            pre_average=parameters["preAverageSeconds"],
            pre_maximum=parameters["preMaximumSeconds"],
            combine=parameters["combineSeconds"],
            offset=parameters["offsetSeconds"],
        )
        for index, value in enumerate(
            _counts(references[(track, class_index)], predictions, tolerance)
        ):
            totals[index] += value
    frozen = (totals[0], totals[1], totals[2])
    return _f1(frozen), frozen


def _calibrate_class(
    *,
    tracks: tuple[str, ...],
    activations: dict[str, np.ndarray],
    references: dict[tuple[str, int], list[float]],
    class_index: int,
    tolerance: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    midi_note = int(LABELS_5[class_index])
    best_parameters: dict[str, float] | None = None
    best_score = -1.0
    best_counts = (0, 0, 0)
    # Preserve ADTOF's official peak-shape parameters. Only confidence and the
    # small systematic timing offset are domain-calibrated; this keeps the
    # search compact and reduces overfitting risk on twelve training songs.
    for threshold in np.arange(0.08, 0.501, 0.01):
        base = {
            "threshold": round(float(threshold), 3),
            "preAverageSeconds": 0.1,
            "preMaximumSeconds": 0.02,
            "combineSeconds": 0.02,
            "offsetSeconds": 0.0,
        }
        for offset in np.arange(-0.03, 0.031, 0.01):
            parameters = {**base, "offsetSeconds": round(float(offset), 3)}
            score, counts = _aggregate_class_score(
                tracks=tracks,
                activations=activations,
                references=references,
                class_index=class_index,
                parameters=parameters,
                tolerance=tolerance,
            )
            # Prefer the default-like, simpler setting on exact ties.
            distance = abs(parameters["threshold"] - DEFAULT_THRESHOLDS[midi_note])
            best_distance = (
                abs(best_parameters["threshold"] - DEFAULT_THRESHOLDS[midi_note])
                if best_parameters is not None
                else float("inf")
            )
            if score > best_score or (score == best_score and distance < best_distance):
                best_score = score
                best_parameters = parameters
                best_counts = counts
    assert best_parameters is not None
    return best_parameters, {
        "f1": best_score,
        "tp": best_counts[0],
        "fp": best_counts[1],
        "fn": best_counts[2],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/research-corpus/MDBDrums/MDB Drums"),
    )
    parser.add_argument("--audio-root", type=Path, default=Path("audio/drum_only"))
    parser.add_argument("--audio-suffix", default="_DR.wav")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--midi-output", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--tolerance-ms", type=int, default=50)
    parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Score only references before this time for excerpt calibration.",
    )
    args = parser.parse_args()

    dataset = args.dataset.resolve(strict=True)
    audio_root = args.audio_root
    if not audio_root.is_absolute():
        audio_root = dataset / audio_root
    audio_root = audio_root.resolve(strict=True)
    weights = args.weights.resolve(strict=True)
    device = args.device
    destination = args.output.resolve()
    if destination.exists():
        raise FileExistsError(destination)
    midi_output = args.midi_output.resolve()
    if midi_output.exists():
        raise FileExistsError(midi_output)

    model = create_frame_rnn_model(calculate_n_bins())
    model = load_pytorch_weights(model, str(weights), strict=False)
    model.eval().to(device)
    all_tracks = TRAIN_TRACKS + TEST_TRACKS
    activations = _load_or_create_activations(
        tracks=all_tracks,
        audio_root=audio_root,
        audio_suffix=args.audio_suffix,
        cache_root=args.cache.resolve(),
        model=model,
        device=device,
    )

    annotation_root = dataset / "annotations" / "class"
    references = {
        (track, class_index): _reference_times(
            annotation_root / f"{track}_class.txt",
            MIDI_TO_MDB[int(midi_note)],
            max_seconds=args.max_seconds,
        )
        for track in TRAIN_TRACKS
        for class_index, midi_note in enumerate(LABELS_5)
    }
    tolerance = args.tolerance_ms / 1000
    parameters: dict[str, dict[str, float]] = {}
    training_metrics: dict[str, Any] = {}
    for class_index, midi_note in enumerate(LABELS_5):
        selected, metrics = _calibrate_class(
            tracks=TRAIN_TRACKS,
            activations=activations,
            references=references,
            class_index=class_index,
            tolerance=tolerance,
        )
        parameters[str(midi_note)] = selected
        training_metrics[str(midi_note)] = metrics
        print(
            json.dumps(
                {"midiNote": midi_note, "parameters": selected, "metrics": metrics}
            ),
            flush=True,
        )

    midi_output.mkdir(parents=True, exist_ok=True)
    prediction_counts: dict[str, dict[str, int]] = {}
    for track in all_tracks:
        peaks: dict[int, list[float]] = {}
        for class_index, midi_note in enumerate(LABELS_5):
            selected = parameters[str(midi_note)]
            peaks[int(midi_note)] = _pick(
                activations[track],
                class_index,
                threshold=selected["threshold"],
                pre_average=selected["preAverageSeconds"],
                pre_maximum=selected["preMaximumSeconds"],
                combine=selected["combineSeconds"],
                offset=selected["offsetSeconds"],
            )
        midi = activations_to_pretty_midi(peaks)
        midi.write(str(midi_output / f"{track}_adtof-calibrated.mid"))
        prediction_counts[track] = {
            str(note): len(times) for note, times in peaks.items()
        }

    payload = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "experiment": {
            "name": "ADTOF MDB train-only decoder calibration",
            "researchOnly": True,
            "datasetLicense": "CC BY-NC-SA 4.0",
            "testLabelsUsedForSelection": False,
            "objectiveToleranceMs": args.tolerance_ms,
            "maxSeconds": args.max_seconds,
            "audioRoot": str(audio_root),
            "audioSuffix": args.audio_suffix,
            "weightsSha256": _sha256(weights),
            "trainingTracks": list(TRAIN_TRACKS),
            "testTracks": list(TEST_TRACKS),
        },
        "parametersByMidiNote": parameters,
        "trainingMetricsByMidiNote": training_metrics,
        "trainingMacroF1": statistics.fmean(
            item["f1"] for item in training_metrics.values()
        ),
        "predictionCounts": prediction_counts,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
