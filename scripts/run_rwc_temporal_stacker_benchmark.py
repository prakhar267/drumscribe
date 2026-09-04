#!/usr/bin/env python3
"""Evaluate the frozen research v20 temporal stacker on an RWC partition."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.temporal_stacker import (
    EventFusionRule,
    StackerDecoderRule,
    build_temporal_stacker,
    decode_stacker_probabilities,
    fuse_event_streams,
    temporal_context_features,
)
from drumscribe_ml.training import TRAINING_CLASSES

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import score_taxonomies, sha256
from run_rwc_popular_50_benchmark import (
    TOLERANCES,
    aggregate_scores,
    load_and_validate_manifest,
    reference_events_from_track,
    write_json,
)

DEFAULT_DATA_ROOT = Path("data/research-corpus/rwc-popular-holdout-39-v1")
DEFAULT_PROBABILITY_ROOT = Path("output/rwc-popular-holdout-39-v20/probabilities")
DEFAULT_BASE_ROOT = Path("output/rwc-popular-holdout-39-v19/drumscribe-raw")
DEFAULT_CONFIG = Path("ml/configs/rwc-temporal-stacker-v20.json")
DEFAULT_OUTPUT = Path("output/rwc-popular-holdout-39-v20/benchmark-result.json")
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument(
        "--probability-root", type=Path, default=DEFAULT_PROBABILITY_ROOT
    )
    parser.add_argument("--base-root", type=Path, default=DEFAULT_BASE_ROOT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def choose_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def aggregate_groups(
    references: dict[str, dict[str, list[list[Event]]]],
    predictions: dict[str, dict[str, list[list[Event]]]],
) -> dict[str, Any]:
    return {
        group: {
            value: {
                "trackCount": len(grouped),
                "scores": aggregate_scores(grouped, predictions[group][value]),
            }
            for value, grouped in sorted(values.items())
        }
        for group, values in references.items()
    }


def main() -> int:
    import torch

    args = parse_args()
    repository = args.repository.resolve(strict=True)
    data_root = resolve(repository, args.data_root)
    probability_root = resolve(repository, args.probability_root)
    base_root = resolve(repository, args.base_root)
    config_path = resolve(repository, args.config)
    output_path = resolve(repository, args.output, strict=False)
    _, manifest = load_and_validate_manifest(data_root)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if int(config.get("schemaVersion", 0)) != 1:
        raise RuntimeError("temporal stacker config requires schemaVersion 1")
    checkpoint_path = resolve(repository, Path(config["checkpoint"]["path"]))
    if sha256(checkpoint_path) != config["checkpoint"]["sha256"]:
        raise RuntimeError("temporal stacker checkpoint hash mismatch")
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    if state["modelVersion"] != config["modelVersion"]:
        raise RuntimeError("temporal stacker model version mismatch")
    selected_device = choose_device(args.device)
    model = build_temporal_stacker(
        int(state["inputSize"]),
        hidden_sizes=tuple(int(value) for value in state["hiddenSizes"]),
        dropout=float(state["dropout"]),
    ).to(selected_device)
    model.load_state_dict(state["model"])
    model.eval()
    mean = state["normalizationMean"].cpu().numpy()
    standard_deviation = state["normalizationStandardDeviation"].cpu().numpy()
    source_order = tuple(config["features"]["sourceOrder"])
    offsets = tuple(int(value) for value in config["features"]["offsetFrames"])
    frame_seconds = float(config["features"]["frameSeconds"])
    decoder_rules = {
        name: StackerDecoderRule(
            threshold=float(rule["threshold"]),
            peak_distance_frames=int(rule["peakDistanceFrames"]),
            onset_shift_frames=int(rule["onsetShiftFrames"]),
        )
        for name, rule in config["stackerDecoderRules"].items()
    }
    fusion_rules = {
        name: EventFusionRule(
            mode=rule["mode"],
            radius_seconds=int(rule["radiusFrames"]) * frame_seconds,
        )
        for name, rule in config["fusionRules"].items()
    }

    references: list[list[Event]] = []
    predictions: list[list[Event]] = []
    baselines: list[list[Event]] = []
    aligned_baselines: list[list[Event]] = []
    grouped_reference: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    grouped_prediction: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    raw_root = output_path.parent / "drumscribe-raw"
    track_rows: list[dict[str, Any]] = []
    for sequence, track in enumerate(manifest["tracks"], 1):
        rwc_id = track["rwcId"]
        sources: dict[str, np.ndarray] = {}
        for source in source_order:
            cache_path = probability_root / source / f"{rwc_id}.npz"
            with np.load(cache_path, allow_pickle=False) as arrays:
                sources[source] = arrays["probabilities"].astype(np.float32)
                if not np.isclose(float(arrays["frame_seconds"]), frame_seconds):
                    raise RuntimeError(f"probability frame rate mismatch: {cache_path}")
        context = temporal_context_features(
            sources,
            source_order=source_order,
            offsets=offsets,
            clip_epsilon=float(config["features"]["clipEpsilon"]),
        )
        if context.shape[1] != len(mean):
            raise RuntimeError("temporal stacker input width mismatch")
        with torch.no_grad():
            probability = (
                torch.sigmoid(
                    model(
                        torch.from_numpy((context - mean) / standard_deviation).to(
                            selected_device
                        )
                    )
                )
                .cpu()
                .numpy()
            )
        decoded = decode_stacker_probabilities(probability, decoder_rules)
        stacker_events = sorted(
            (frame * frame_seconds, instrument.value)
            for instrument in TRAINING_CLASSES
            for frame in decoded[instrument.value]
        )
        raw_base = json.loads(
            (base_root / f"{rwc_id}.json").read_text(encoding="utf-8")
        )
        baseline = sorted(
            (float(hit["onsetSeconds"]), str(hit["instrument"]))
            for hit in raw_base["hits"]
        )
        aligned = sorted(
            (
                onset + int(config["baseOnsetShiftFrames"][instrument]) * frame_seconds,
                instrument,
            )
            for onset, instrument in baseline
            if 0
            <= onset + int(config["baseOnsetShiftFrames"][instrument]) * frame_seconds
            < float(track["clipDurationSeconds"])
        )
        prediction = fuse_event_streams(aligned, stacker_events, fusion_rules)
        reference = reference_events_from_track(track)
        references.append(reference)
        predictions.append(prediction)
        baselines.append(baseline)
        aligned_baselines.append(aligned)
        for group in grouped_reference:
            key = str(track[group])
            grouped_reference[group][key].append(reference)
            grouped_prediction[group][key].append(prediction)
        raw_path = raw_root / f"{rwc_id}.json"
        write_json(
            raw_path,
            {
                "schemaVersion": 1,
                "provider": "drumscribe-temporal-stacker-v20-research",
                "modelVersion": config["modelVersion"],
                "productionApproved": False,
                "hits": [
                    {"onsetSeconds": round(onset, 6), "instrument": instrument}
                    for onset, instrument in prediction
                ],
            },
        )
        track_scores = {
            str(round(tolerance * 1_000)): score_taxonomies(
                reference, prediction, tolerance
            )
            for tolerance in TOLERANCES
        }
        track_rows.append(
            {
                "sequence": sequence,
                "rwcId": rwc_id,
                "title": track["title"],
                "artist": track["artist"],
                "drumType": track["drumType"],
                "language": track["language"],
                "referenceEventCount": len(reference),
                "predictionEventCount": len(prediction),
                "scores": track_scores,
                "predictionSha256": sha256(raw_path),
            }
        )
        print(
            json.dumps(
                {
                    "track": f"{sequence}/{len(manifest['tracks'])}",
                    "rwcId": rwc_id,
                    "detailedF1At50ms": track_scores["50"]["detailed14"]["micro"]["f1"],
                }
            ),
            flush=True,
        )

    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "RWC Popular temporal stacker v20 secondary evaluation",
            "status": "previously_opened_secondary_partition",
            "recordCount": len(track_rows),
            "referenceEventCount": manifest["referenceEventCount"],
            "totalScoredAudioSeconds": manifest["totalScoredAudioSeconds"],
            "license": manifest["dataset"]["license"],
            "tolerancesMilliseconds": [round(value * 1_000) for value in TOLERANCES],
        },
        "system": {
            "name": "DrumScribe",
            "modelVersion": config["modelVersion"],
            "productionApproved": False,
            "configSha256": sha256(config_path),
            "checkpointSha256": sha256(checkpoint_path),
            "device": selected_device,
        },
        "aggregate": aggregate_scores(references, predictions),
        "baselineAggregate": aggregate_scores(references, baselines),
        "alignedBaseAggregate": aggregate_scores(references, aligned_baselines),
        "groups": aggregate_groups(grouped_reference, grouped_prediction),
        "tracks": track_rows,
    }
    write_json(output_path, report)
    summary = {
        "output": str(output_path),
        "tracks": len(track_rows),
        "detailedF1At50ms": report["aggregate"]["50"]["detailed14"]["micro"]["f1"],
        "baselineDetailedF1At50ms": report["baselineAggregate"]["50"]["detailed14"][
            "micro"
        ]["f1"],
        "alignedBaseDetailedF1At50ms": report["alignedBaseAggregate"]["50"][
            "detailed14"
        ]["micro"]["f1"],
        "familyF1At50ms": report["aggregate"]["50"]["family6"]["micro"]["f1"],
        "coreF1At50ms": report["aggregate"]["50"]["core3"]["micro"]["f1"],
        "classAgnosticF1At50ms": report["aggregate"]["50"]["detailed14"][
            "classAgnostic"
        ]["f1"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
