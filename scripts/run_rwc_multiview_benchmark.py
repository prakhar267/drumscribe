#!/usr/bin/env python3
"""Evaluate the frozen v19 multi-view candidate on a prepared RWC partition."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import (
    StackedEnsembleConfig,
    decode_stacked_probabilities,
)
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel
from drumscribe_ml.multiview import (
    MultiViewConfig,
    config_evidence,
    decode_multiview_probabilities,
)
from drumscribe_ml.training import TRAINING_CLASSES, TrainingConfig, build_model

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from model_runners.drumscribe_multiview_runner import specialist_probabilities
from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    load_models,
    predict_stacked_probabilities,
    score_taxonomies,
    sha256,
)
from run_rwc_popular_50_benchmark import (
    TOLERANCES,
    aggregate_scores,
    load_and_validate_manifest,
    reference_events_from_track,
    write_json,
)

DEFAULT_DATA_ROOT = Path("data/research-corpus/rwc-popular-50-v1")
DEFAULT_OUTPUT = Path("output/rwc-popular-50-v19-development/benchmark-result.json")
DEFAULT_MULTIVIEW_CONFIG = Path("ml/configs/groove-multiview-articulation-v19.json")
DEFAULT_ENSEMBLE_CONFIG = Path("ml/configs/groove-stacked-articulation-v18.json")
DEFAULT_SPECIALIST = Path("ml/models/groove-egmd-focal-specialist-v18.pt")
Event = tuple[float, str]


def _resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def _device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _aggregate_groups(
    references: dict[str, list[list[Event]]],
    predictions: dict[str, list[list[Event]]],
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


def evaluate(args: argparse.Namespace) -> int:
    import torch

    repository = args.repository.resolve(strict=True)
    data_root = _resolve(repository, args.data_root)
    output_path = _resolve(repository, args.output, strict=False)
    multiview_path = _resolve(repository, args.multiview_config)
    ensemble_path = _resolve(repository, args.ensemble_config)
    specialist_path = _resolve(repository, args.specialist_checkpoint)
    manifest_path, manifest = load_and_validate_manifest(data_root)
    separation_path = (data_root / "separation-manifest.json").resolve(strict=True)
    separation = json.loads(separation_path.read_text(encoding="utf-8"))
    if separation["sourceSelectionManifestSha256"] != sha256(manifest_path):
        raise RuntimeError("separation manifest does not match frozen selection")
    stems = {item["rwcId"]: item for item in separation["stems"]}

    fusion = MultiViewConfig.load(multiview_path)
    evidence = config_evidence(multiview_path)
    components = evidence["components"]
    if components["stackedEnsemble"]["sha256"] != sha256(ensemble_path):
        raise RuntimeError("ensemble config hash does not match the frozen v19 config")
    if components["focalSpecialist"]["sha256"] != sha256(specialist_path):
        raise RuntimeError("specialist hash does not match the frozen v19 config")
    ensemble = StackedEnsembleConfig.load(ensemble_path)
    selected_device = _device(args.device)

    feature_roots = {
        "stem": data_root / "features" / separation["model"],
        "mixture": data_root / "features" / "full-mix",
    }
    preparation = PreparationConfig(
        seed="rwc-multiview-v19-inference", augmentation_variants=0
    )
    feature_paths: dict[str, dict[str, Path]] = {"stem": {}, "mixture": {}}
    for track in manifest["tracks"]:
        rwc_id = track["rwcId"]
        sources = {
            "stem": (data_root / stems[rwc_id]["drumsRelativePath"]).resolve(
                strict=True
            ),
            "mixture": (data_root / track["clipRelativePath"]).resolve(strict=True),
        }
        if sha256(sources["stem"]) != stems[rwc_id]["drumsSha256"]:
            raise RuntimeError(f"separated stem checksum mismatch: {rwc_id}")
        for view, source in sources.items():
            feature = feature_roots[view] / f"{rwc_id}.npz"
            if not feature.exists():
                cache_log_mel(source, feature, preparation)
            feature_paths[view][rwc_id] = feature

    first_feature = feature_paths["stem"][manifest["tracks"][0]["rwcId"]]
    with np.load(first_feature, allow_pickle=False) as arrays:
        mel_bands = int(arrays["features"].shape[1])
    checkpoint_paths = {
        name: _resolve(repository, CHECKPOINTS[name]) for name in ensemble.models
    }
    ensemble_models = load_models(
        ensemble, checkpoint_paths, mel_bands, selected_device
    )
    specialist_state = torch.load(
        specialist_path, map_location="cpu", weights_only=True
    )
    specialist_configuration = TrainingConfig(**specialist_state["configuration"])
    specialist = build_model(
        specialist_configuration,
        mel_bands=mel_bands,
        class_count=len(TRAINING_CLASSES),
    ).to(selected_device)
    specialist.load_state_dict(specialist_state["model"])
    specialist.eval()

    all_reference: list[list[Event]] = []
    all_prediction: list[list[Event]] = []
    all_baseline: list[list[Event]] = []
    grouped_reference: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    grouped_prediction: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    raw_root = output_path.parent / "drumscribe-raw"
    probability_cache_root = (
        _resolve(repository, args.probability_cache_root, strict=False)
        if args.probability_cache_root is not None
        else None
    )
    tracks: list[dict[str, Any]] = []
    class_index = {
        instrument.value: index for index, instrument in enumerate(TRAINING_CLASSES)
    }
    for sequence, track in enumerate(manifest["tracks"], 1):
        rwc_id = track["rwcId"]
        duration = float(track["clipDurationSeconds"])
        sources: dict[str, np.ndarray] = {}
        frame_seconds: float | None = None
        stem_stacked: np.ndarray | None = None
        for view in ("stem", "mixture"):
            stacked, stacked_frame_seconds = predict_stacked_probabilities(
                feature_paths[view][rwc_id],
                ensemble_models,
                ensemble,
                selected_device,
                duration,
            )
            focal, focal_frame_seconds = specialist_probabilities(
                feature_paths[view][rwc_id],
                specialist,
                device=selected_device,
                limit=duration,
            )
            if not math.isclose(stacked_frame_seconds, focal_frame_seconds):
                raise RuntimeError("multi-view frame rates do not match")
            frame_seconds = stacked_frame_seconds
            sources[f"{view}Ensemble"] = stacked
            sources[f"{view}Specialist"] = focal
            if view == "stem":
                stem_stacked = stacked
        assert frame_seconds is not None and stem_stacked is not None
        if probability_cache_root is not None:
            for source_name, source_probabilities in sources.items():
                destination = probability_cache_root / source_name / f"{rwc_id}.npz"
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                with temporary.open("wb") as handle:
                    np.savez_compressed(
                        handle,
                        probabilities=source_probabilities.astype(np.float32),
                        frame_seconds=np.asarray(frame_seconds, dtype=np.float64),
                    )
                temporary.replace(destination)
        probabilities, decoded = decode_multiview_probabilities(sources, fusion.rules)
        baseline_decoded = decode_stacked_probabilities(
            stem_stacked,
            ensemble.rules,
            family_conflict_margins=ensemble.family_conflict_margins,
        )
        prediction = sorted(
            (
                frame * frame_seconds,
                instrument.value,
            )
            for instrument in TRAINING_CLASSES
            for frame in decoded[instrument.value]
            if frame * frame_seconds < duration
        )
        baseline = sorted(
            (frame * frame_seconds, instrument.value)
            for instrument in TRAINING_CLASSES
            for frame in baseline_decoded[instrument.value]
            if frame * frame_seconds < duration
        )
        reference = reference_events_from_track(track)
        all_reference.append(reference)
        all_prediction.append(prediction)
        all_baseline.append(baseline)
        for group in grouped_reference:
            key = str(track[group])
            grouped_reference[group][key].append(reference)
            grouped_prediction[group][key].append(prediction)
        raw_path = raw_root / f"{rwc_id}.json"
        write_json(
            raw_path,
            {
                "schemaVersion": 1,
                "provider": "drumscribe-multiview-v19-development",
                "modelVersion": fusion.model_version,
                "productionApproved": fusion.production_approved,
                "source": {
                    "mixtureSha256": track["clipSha256"],
                    "drumStemSha256": stems[rwc_id]["drumsSha256"],
                },
                "hits": [
                    {
                        "onsetSeconds": round(onset, 6),
                        "instrument": instrument,
                        "confidence": round(
                            float(
                                probabilities[
                                    round(onset / frame_seconds),
                                    class_index[instrument],
                                ]
                            ),
                            7,
                        ),
                    }
                    for onset, instrument in prediction
                ],
            },
        )
        scores = {
            str(round(tolerance * 1_000)): score_taxonomies(
                reference, prediction, tolerance
            )
            for tolerance in TOLERANCES
        }
        tracks.append(
            {
                "sequence": sequence,
                "rwcId": rwc_id,
                "title": track["title"],
                "artist": track["artist"],
                "language": track["language"],
                "drumType": track["drumType"],
                "genreMain": track["genreMain"],
                "genreSub": track["genreSub"],
                "referenceEventCount": len(reference),
                "predictionEventCount": len(prediction),
                "baselineEventCount": len(baseline),
                "predictionSha256": sha256(raw_path),
                "scores": scores,
                "baselineScores": {
                    str(round(tolerance * 1_000)): score_taxonomies(
                        reference, baseline, tolerance
                    )
                    for tolerance in TOLERANCES
                },
            }
        )
        print(
            json.dumps(
                {
                    "predicted": rwc_id,
                    "track": f"{sequence}/{len(manifest['tracks'])}",
                    "detailedF1At50ms": scores["50"]["detailed14"]["micro"]["f1"],
                }
            ),
            flush=True,
        )

    selection_offset = int(manifest.get("selectionOffset", 0))
    holdout = selection_offset > 0
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "RWC Popular multi-view transcription evaluation",
            "status": (
                "previously_untouched_holdout_opened_by_this_run"
                if holdout
                else "opened_development_calibration_replay"
            ),
            "recordCount": len(tracks),
            "selectionOffset": selection_offset,
            "totalScoredAudioSeconds": manifest["totalScoredAudioSeconds"],
            "referenceEventCount": manifest["referenceEventCount"],
            "selectionManifestSha256": sha256(manifest_path),
            "selectionReferenceSha256": manifest["selectionReferenceSha256"],
            "license": manifest["dataset"]["license"],
            "matcher": "one-to-one class-aware onset matching",
            "tolerancesMilliseconds": [round(value * 1_000) for value in TOLERANCES],
            "limitations": [
                *manifest["limitations"],
                "The v19 decoder was calibrated on the disjoint first 50 RWC selections.",
                "The CC BY-NC corpus and research Demucs path cannot authorize commercial deployment.",
                "This scores transcription events, not beat-grid or engraving quality.",
            ],
        },
        "system": {
            "name": "DrumScribe",
            "pipeline": (
                f"{separation['model']} drum stem + original mixture -> fixed v19 multi-view fusion"
            ),
            "modelVersion": fusion.model_version,
            "productionApproved": fusion.production_approved,
            "multiviewConfigSha256": sha256(multiview_path),
            "ensembleConfigSha256": sha256(ensemble_path),
            "specialistCheckpointSha256": sha256(specialist_path),
            "checkpointSha256": {
                name: sha256(path) for name, path in sorted(checkpoint_paths.items())
            },
            "device": selected_device,
            "separationManifestSha256": sha256(separation_path),
        },
        "aggregate": aggregate_scores(all_reference, all_prediction),
        "baselineAggregate": aggregate_scores(all_reference, all_baseline),
        "groups": _aggregate_groups(grouped_reference, grouped_prediction),
        "tracks": tracks,
    }
    write_json(output_path, report)
    summary = {
        "output": str(output_path),
        "status": report["benchmark"]["status"],
        "tracks": len(tracks),
        "referenceEvents": manifest["referenceEventCount"],
        "detailedF1At50ms": report["aggregate"]["50"]["detailed14"]["micro"]["f1"],
        "familyF1At50ms": report["aggregate"]["50"]["family6"]["micro"]["f1"],
        "coreF1At50ms": report["aggregate"]["50"]["core3"]["micro"]["f1"],
        "classAgnosticF1At50ms": report["aggregate"]["50"]["detailed14"][
            "classAgnostic"
        ]["f1"],
        "baselineDetailedF1At50ms": report["baselineAggregate"]["50"]["detailed14"][
            "micro"
        ]["f1"],
        "detailedGainPercentagePoints": 100
        * (
            report["aggregate"]["50"]["detailed14"]["micro"]["f1"]
            - report["baselineAggregate"]["50"]["detailed14"]["micro"]["f1"]
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--multiview-config", type=Path, default=DEFAULT_MULTIVIEW_CONFIG
    )
    parser.add_argument("--ensemble-config", type=Path, default=DEFAULT_ENSEMBLE_CONFIG)
    parser.add_argument(
        "--specialist-checkpoint", type=Path, default=DEFAULT_SPECIALIST
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    parser.add_argument(
        "--probability-cache-root",
        type=Path,
        help="optional directory for the four aligned frame-probability streams",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(evaluate(parse_args()))
