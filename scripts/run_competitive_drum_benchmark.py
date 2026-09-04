#!/usr/bin/env python3
"""Run a reproducible, like-for-like DrumScribe versus MusicJSON benchmark.

The benchmark intentionally uses the first 20 seconds of ten rights-cleared
Groove test performances.  Both systems are scored against the same canonical
MIDI-derived events with the same one-to-one onset matcher.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import (
    StackedEnsembleConfig,
    blend_stacked_probabilities,
    decode_stacked_probabilities,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingConfig, build_model
from drumscribe_music.mapping import GM_TO_INSTRUMENT

DEFAULT_CONFIG = Path("ml/configs/groove-stacked-articulation-v16.json")
DEFAULT_PREPARED = Path("data/licensed-corpus/groove-prepared/prepared-dataset.json")
DEFAULT_COMPETITOR = Path("output/competitive-benchmark-2026-09-02/klangio-raw")
DEFAULT_OUTPUT = Path("output/competitive-benchmark-2026-09-02/benchmark-result.json")
WINDOW_SECONDS = 20.0
TOLERANCES = (0.02, 0.05)
CORE_THREE_MAP = {
    "KICK": "KICK",
    "SNARE": "SNARE",
    "CROSS_STICK": "SNARE",
    "CLOSED_HIHAT": "HIHAT",
    "OPEN_HIHAT": "HIHAT",
    "PEDAL_HIHAT": "HIHAT",
}
FAMILY_SIX_MAP = {
    **CORE_THREE_MAP,
    "RIDE": "CYMBAL",
    "RIDE_BELL": "CYMBAL",
    "CRASH": "CYMBAL",
    "HIGH_TOM": "TOM",
    "MID_TOM": "TOM",
    "LOW_TOM": "TOM",
    "FLOOR_TOM": "TOM",
    "TAMBOURINE": "TAMBOURINE",
}
CHECKPOINTS = {
    "c14": Path(
        "data/licensed-corpus/experiments/"
        "groove-oaf-open-cymbal-specialist-v15/checkpoint-0014.pt"
    ),
    "e3": Path(
        "data/licensed-corpus/experiments/"
        "groove-oaf-cnn-articulation-v9/checkpoint-0003.pt"
    ),
    "e4": Path(
        "data/licensed-corpus/experiments/"
        "groove-oaf-cnn-articulation-v9/checkpoint-0004.pt"
    ),
    "s15": Path(
        "data/licensed-corpus/experiments/"
        "groove-oaf-articulation-specialist-v14/checkpoint-0015.pt"
    ),
    "v10": Path(
        "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/best.pt"
    ),
    "v12": Path(
        "data/licensed-corpus/experiments/groove-oaf-family-finetune-v12/best.pt"
    ),
    "v7": Path("data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/best.pt"),
    "w15": Path(
        "data/licensed-corpus/experiments/"
        "groove-egmd-weak-class-specialist-v17/checkpoint-0015.pt"
    ),
}


Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--competitor", type=Path, default=DEFAULT_COMPETITOR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--window-seconds", type=float, default=WINDOW_SECONDS)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve(repository: Path, path: Path) -> Path:
    return (
        (repository / path).resolve(strict=True)
        if not path.is_absolute()
        else path.resolve(strict=True)
    )


def select_records(prepared_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    selected: dict[int, dict[str, Any]] = {}
    for record in payload["records"]:
        audio_path = Path(record["audioPath"])
        match = re.search(r"drummer1/eval_session/(\d+)_", audio_path.as_posix())
        if match and record.get("split") == "test":
            selected[int(match.group(1))] = record
    expected = set(range(1, 11))
    if set(selected) != expected:
        raise RuntimeError(
            f"expected Groove eval recordings 1..10; found {sorted(selected)}"
        )
    # Keep the same filename order used by the ten live submissions.
    return [selected[index] for index in (1, 10, 2, 3, 4, 5, 6, 7, 8, 9)]


def reference_events(path: Path, limit: float) -> list[Event]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        (float(event["onsetSeconds"]), str(event["instrument"]))
        for event in payload["events"]
        if 0 <= float(event["onsetSeconds"]) < limit
    )


def competitor_events(path: Path, limit: float) -> tuple[list[Event], float]:
    """Decode the audio-aligned score data used by the public result viewer.

    Measure ``TimeStamp`` values are used instead of deriving time from the
    displayed rounded BPM.  This preserves the service's own audio alignment.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    global_tempo = float(payload["MusicInfo"]["Tempo"])
    events: list[Event] = []
    for part in payload.get("Parts", []):
        measures = part.get("Measures", [])
        for measure_index, measure in enumerate(measures):
            start = float(measure.get("TimeStamp", 0.0))
            if measure_index + 1 < len(measures):
                end = float(measures[measure_index + 1].get("TimeStamp", start))
                span = end - start
            else:
                local_tempo = float(measure.get("Tempo") or global_tempo)
                span = 4.0 * 60.0 / local_tempo
            if not math.isfinite(span) or span <= 0:
                span = 4.0 * 60.0 / global_tempo
            for voice in measure.get("Voices", []):
                cursor = 0.0
                for note in voice.get("Notes", []):
                    onset = start + cursor * span
                    instruments = {
                        GM_TO_INSTRUMENT[midi].value
                        for midi in note.get("Midi", [])
                        if isinstance(midi, int) and midi in GM_TO_INSTRUMENT
                    }
                    if 0 <= onset < limit:
                        events.extend((onset, instrument) for instrument in instruments)
                    cursor += float(note.get("Duration", 0.0))
    return sorted(events), global_tempo


def choose_device(torch: Any, requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_models(
    config: StackedEnsembleConfig,
    checkpoint_paths: dict[str, Path],
    mel_bands: int,
    device: str,
) -> dict[str, Any]:
    import torch

    models: dict[str, Any] = {}
    missing = sorted(set(config.models) - set(checkpoint_paths))
    if missing:
        raise RuntimeError(f"missing checkpoint paths for configured models: {missing}")
    for name in config.models:
        checkpoint_path = checkpoint_paths[name]
        expected = config.models[name].sha256
        actual = sha256(checkpoint_path)
        if actual != expected:
            raise RuntimeError(
                f"checkpoint hash mismatch for {name}: {actual} != {expected}"
            )
        state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
        model_config = TrainingConfig(**state["configuration"])
        model = build_model(
            model_config,
            mel_bands=mel_bands,
            class_count=len(TRAINING_CLASSES),
        ).to(device)
        model.load_state_dict(state["model"])
        model.eval()
        models[name] = model
    return models


def predict_drumscribe(
    feature_path: Path,
    models: dict[str, Any],
    config: StackedEnsembleConfig,
    device: str,
    limit: float,
) -> list[Event]:
    probabilities, frame_seconds = predict_stacked_probabilities(
        feature_path, models, config, device, limit
    )
    decoded = decode_stacked_probabilities(
        probabilities,
        config.rules,
        family_conflict_margins=config.family_conflict_margins,
    )
    return sorted(
        (frame * frame_seconds, instrument.value)
        for instrument in TRAINING_CLASSES
        for frame in decoded[instrument.value]
        if frame * frame_seconds < limit
    )


def predict_stacked_probabilities(
    feature_path: Path,
    models: dict[str, Any],
    config: StackedEnsembleConfig,
    device: str,
    limit: float,
) -> tuple[np.ndarray, float]:
    """Return the fused frame probabilities before threshold decoding."""
    import torch

    with np.load(feature_path, allow_pickle=False) as arrays:
        features = arrays["features"].astype(np.float32)
        hop_length = int(arrays["hop_length"])
        sample_rate = int(arrays["sample_rate"])
    maximum_frames = min(features.shape[0], math.ceil(limit * sample_rate / hop_length))
    feature_tensor = torch.from_numpy(features[:maximum_frames])[None].to(device)
    with torch.no_grad():
        probabilities_by_model = {
            name: torch.sigmoid(model(feature_tensor)[0])[0].cpu().numpy()
            for name, model in models.items()
        }
    probabilities = blend_stacked_probabilities(probabilities_by_model, config.rules)
    return probabilities, hop_length / sample_rate


def match_times(
    references: Iterable[float], predictions: Iterable[float], tolerance: float
) -> dict[str, Any]:
    refs = sorted(references)
    preds = sorted(predictions)
    ref_index = pred_index = true_positive = false_positive = false_negative = 0
    errors: list[float] = []
    while ref_index < len(refs) and pred_index < len(preds):
        reference = refs[ref_index]
        prediction = preds[pred_index]
        if prediction < reference - tolerance:
            false_positive += 1
            pred_index += 1
        elif reference < prediction - tolerance:
            false_negative += 1
            ref_index += 1
        else:
            true_positive += 1
            errors.append(abs(prediction - reference))
            ref_index += 1
            pred_index += 1
    false_negative += len(refs) - ref_index
    false_positive += len(preds) - pred_index
    return {
        "tp": true_positive,
        "fp": false_positive,
        "fn": false_negative,
        "errors": errors,
    }


def metrics_from_counts(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score(
    reference: list[Event], prediction: list[Event], tolerance: float
) -> dict[str, Any]:
    classes = sorted(
        {label for _, label in reference} | {label for _, label in prediction}
    )
    by_class: dict[str, dict[str, Any]] = {}
    aggregate = {"tp": 0, "fp": 0, "fn": 0}
    all_errors: list[float] = []
    supported_f1: list[float] = []
    for instrument in classes:
        references = [time for time, label in reference if label == instrument]
        predictions = [time for time, label in prediction if label == instrument]
        matched = match_times(references, predictions, tolerance)
        metrics = metrics_from_counts(matched["tp"], matched["fp"], matched["fn"])
        metrics["support"] = len(references)
        if matched["errors"]:
            metrics["meanAbsoluteTimingErrorMs"] = (
                statistics.mean(matched["errors"]) * 1000
            )
        by_class[instrument] = metrics
        for key in aggregate:
            aggregate[key] += int(matched[key])
        all_errors.extend(matched["errors"])
        if references:
            supported_f1.append(float(metrics["f1"]))
    micro = metrics_from_counts(**aggregate)
    onset = match_times(
        (time for time, _ in reference),
        (time for time, _ in prediction),
        tolerance,
    )
    result: dict[str, Any] = {
        "micro": micro,
        "supportedMacroF1": statistics.mean(supported_f1) if supported_f1 else 0.0,
        "supportedClassCount": len(supported_f1),
        "classAgnostic": metrics_from_counts(onset["tp"], onset["fp"], onset["fn"]),
        "referenceEvents": len(reference),
        "predictedEvents": len(prediction),
        "perClass": by_class,
    }
    if all_errors:
        result["meanAbsoluteTimingErrorMs"] = statistics.mean(all_errors) * 1000
        result["medianAbsoluteTimingErrorMs"] = statistics.median(all_errors) * 1000
    return result


def combine_event_lists(items: list[list[Event]], stride: float = 100.0) -> list[Event]:
    return [
        (time + index * stride, instrument)
        for index, events in enumerate(items)
        for time, instrument in events
    ]


def mapped_events(events: list[Event], mapping: dict[str, str]) -> list[Event]:
    return [
        (time, mapping[instrument])
        for time, instrument in events
        if instrument in mapping
    ]


def score_taxonomies(
    reference: list[Event], prediction: list[Event], tolerance: float
) -> dict[str, Any]:
    return {
        "detailed14": score(reference, prediction, tolerance),
        "family6": score(
            mapped_events(reference, FAMILY_SIX_MAP),
            mapped_events(prediction, FAMILY_SIX_MAP),
            tolerance,
        ),
        "core3": score(
            mapped_events(reference, CORE_THREE_MAP),
            mapped_events(prediction, CORE_THREE_MAP),
            tolerance,
        ),
    }


def bpm_from_filename(path: Path) -> float:
    match = re.search(r"_(\d+)_beat_", path.name)
    if not match:
        raise RuntimeError(f"cannot read reference BPM from {path.name}")
    return float(match.group(1))


def main() -> None:
    args = parse_args()
    repository = args.repository.resolve(strict=True)
    config_path = resolve(repository, args.config)
    prepared_path = resolve(repository, args.prepared)
    competitor_root = resolve(repository, args.competitor)
    output_path = (
        (repository / args.output).resolve()
        if not args.output.is_absolute()
        else args.output.resolve()
    )
    config = StackedEnsembleConfig.load(config_path)
    records = select_records(prepared_path)
    competitor_paths = sorted(competitor_root.glob("*.json"))
    if len(competitor_paths) != len(records):
        raise RuntimeError(
            f"expected {len(records)} competitor files; found {len(competitor_paths)}"
        )

    import torch

    first_features = np.load(records[0]["featurePath"])["features"]
    device = choose_device(torch, args.device)
    checkpoint_paths = {
        name: resolve(repository, CHECKPOINTS[name]) for name in config.models
    }
    models = load_models(config, checkpoint_paths, int(first_features.shape[1]), device)

    all_reference: list[list[Event]] = []
    all_drumscribe: list[list[Event]] = []
    all_competitor: list[list[Event]] = []
    tracks: list[dict[str, Any]] = []
    bpm_errors: list[float] = []
    drumscribe_raw_root = output_path.parent / "drumscribe-raw"
    drumscribe_raw_root.mkdir(parents=True, exist_ok=True)

    for sequence, (record, competitor_path) in enumerate(
        zip(records, competitor_paths, strict=True), 1
    ):
        audio_path = Path(record["audioPath"]).resolve(strict=True)
        annotation_path = Path(record["annotationPath"]).resolve(strict=True)
        feature_path = Path(record["featurePath"]).resolve(strict=True)
        reference = reference_events(annotation_path, args.window_seconds)
        competitor, estimated_bpm = competitor_events(
            competitor_path, args.window_seconds
        )
        drumscribe = predict_drumscribe(
            feature_path, models, config, device, args.window_seconds
        )
        reference_bpm = bpm_from_filename(audio_path)
        bpm_errors.append(abs(estimated_bpm - reference_bpm))
        all_reference.append(reference)
        all_drumscribe.append(drumscribe)
        all_competitor.append(competitor)
        raw_path = drumscribe_raw_root / f"{sequence:02d}.json"
        raw_path.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "modelVersion": config.model_version,
                    "sourceAudioSha256": sha256(audio_path),
                    "windowSeconds": args.window_seconds,
                    "events": [
                        {"onsetSeconds": time, "instrument": instrument}
                        for time, instrument in drumscribe
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        tracks.append(
            {
                "sequence": sequence,
                "audioFile": audio_path.name,
                "audioSha256": sha256(audio_path),
                "referenceBpm": reference_bpm,
                "competitorEstimatedBpm": estimated_bpm,
                "competitorAbsoluteBpmError": abs(estimated_bpm - reference_bpm),
                "referenceEventCount": len(reference),
                "drumscribeEventCount": len(drumscribe),
                "competitorEventCount": len(competitor),
                "scores": {
                    str(int(tolerance * 1000)): {
                        "drumscribe": score_taxonomies(
                            reference, drumscribe, tolerance
                        ),
                        "drum2notes": score_taxonomies(
                            reference, competitor, tolerance
                        ),
                    }
                    for tolerance in TOLERANCES
                },
            }
        )

    combined_reference = combine_event_lists(all_reference)
    combined_drumscribe = combine_event_lists(all_drumscribe)
    combined_competitor = combine_event_lists(all_competitor)
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Groove eval-session live commercial comparison",
            "status": "comparative_probe_not_sealed",
            "recordCount": len(records),
            "windowSecondsPerRecord": args.window_seconds,
            "totalScoredAudioSeconds": len(records) * args.window_seconds,
            "rightsCleared": True,
            "referenceSource": "Google Magenta Groove MIDI Dataset canonical annotations",
            "inputType": "isolated drum performances",
            "matcher": "one-to-one onset matching",
            "tolerancesMilliseconds": [int(value * 1000) for value in TOLERANCES],
            "limitations": [
                "The ten Groove test recordings were used previously during internal development, so this is not a fresh sealed generalization test.",
                "The inputs are isolated electronic-drum performances; separation quality and full-mixture transcription are outside this comparison.",
                "Drum2Notes was scored from the structured, audio-aligned note data displayed by its public demo result viewer; paid export formats were not accessed.",
            ],
        },
        "systems": {
            "drumscribe": {
                "modelVersion": config.model_version,
                "configSha256": sha256(config_path),
                "checkpointSha256": {
                    name: sha256(path)
                    for name, path in sorted(checkpoint_paths.items())
                },
                "device": device,
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes live demo",
                "runDate": "2026-09-02",
                "rawResultSha256": [sha256(path) for path in competitor_paths],
                "tempoMeanAbsoluteErrorBpm": statistics.mean(bpm_errors),
                "tempoMedianAbsoluteErrorBpm": statistics.median(bpm_errors),
            },
        },
        "aggregate": {
            str(int(tolerance * 1000)): {
                "drumscribe": score_taxonomies(
                    combined_reference, combined_drumscribe, tolerance
                ),
                "drum2notes": score_taxonomies(
                    combined_reference, combined_competitor, tolerance
                ),
            }
            for tolerance in TOLERANCES
        },
        "tracks": tracks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"output": str(output_path), "device": device, "records": len(records)}
        )
    )


if __name__ == "__main__":
    main()
