#!/usr/bin/env python3
"""Run a balanced 100-recording genre benchmark on real human performances.

The corpus is the CC BY 4.0 Google Magenta Groove MIDI Dataset test split.
Every audio performance has an aligned MIDI-derived event reference.  The
selection excludes recordings already used by the earlier ten-item live
Drum2Notes probe, then takes 25 recordings from each of four genre groups.

This is a detector benchmark on isolated electronic-drum recordings.  It does
not measure source separation or performance on complete commercial songs.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    TOLERANCES,
    combine_event_lists,
    load_models,
    predict_drumscribe,
    reference_events,
    score_taxonomies,
    sha256,
)

DEFAULT_CONFIG = Path("ml/configs/groove-stacked-articulation-v16.json")
DEFAULT_PREPARED = Path("data/licensed-corpus/groove-prepared/prepared-dataset.json")
DEFAULT_PRIOR_RESULT = Path(
    "output/competitive-benchmark-2026-09-02/benchmark-result.json"
)
DEFAULT_OUTPUT = Path(
    "output/100-track-genre-benchmark-2026-09-03/benchmark-result.json"
)
WINDOW_SECONDS = 20.0
RECORDS_PER_CATEGORY = 25
CATEGORY_ORDER = (
    "heavy_rock_punk",
    "pop_soul",
    "funk_hiphop",
    "jazz_world",
)

Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--prior-result", type=Path, default=DEFAULT_PRIOR_RESULT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--window-seconds", type=float, default=WINDOW_SECONDS)
    parser.add_argument(
        "--records-per-category", type=int, default=RECORDS_PER_CATEGORY
    )
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


def style_from_audio(path: Path) -> str:
    match = re.match(r"^\d+_(.+)_\d+_(?:beat|fill)_", path.name)
    if not match:
        raise RuntimeError(f"cannot read style from Groove filename: {path.name}")
    return match.group(1)


def category_for_style(style: str) -> str:
    if style == "punk" or "rock" in style:
        return "heavy_rock_punk"
    if style.startswith(("soul", "pop", "country")) or style == "gospel":
        return "pop_soul"
    if style.startswith(("funk", "hiphop")):
        return "funk_hiphop"
    if style.startswith(("jazz", "latin", "afrocuban", "neworleans", "reggae")):
        return "jazz_world"
    raise RuntimeError(f"unmapped Groove style: {style}")


def prior_audio_hashes(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {str(track["audioSha256"]) for track in payload["tracks"]}


def select_records(
    prepared_path: Path, excluded_hashes: set[str], records_per_category: int
) -> list[dict[str, Any]]:
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in payload["records"]:
        if record.get("split") != "test":
            continue
        if str(record["audioSha256"]) in excluded_hashes:
            continue
        audio_path = Path(record["audioPath"])
        style = style_from_audio(audio_path)
        enriched = {**record, "style": style, "category": category_for_style(style)}
        candidates[enriched["category"]].append(enriched)

    selected: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        records = sorted(
            candidates[category],
            key=lambda item: (str(item["style"]), str(item["trackId"])),
        )
        if len(records) < records_per_category:
            raise RuntimeError(
                f"category {category} has {len(records)} eligible records; "
                f"need {records_per_category}"
            )
        selected.extend(records[:records_per_category])
    return selected


def aggregate_scores(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    combined_reference = combine_event_lists(references)
    combined_prediction = combine_event_lists(predictions)
    return {
        str(int(tolerance * 1000)): score_taxonomies(
            combined_reference, combined_prediction, tolerance
        )
        for tolerance in TOLERANCES
    }


def main() -> int:
    args = parse_args()
    if args.records_per_category <= 0:
        raise ValueError("records-per-category must be positive")
    if args.window_seconds <= 0:
        raise ValueError("window-seconds must be positive")

    repository = args.repository.resolve(strict=True)
    config_path = resolve(repository, args.config)
    prepared_path = resolve(repository, args.prepared)
    prior_result_path = resolve(repository, args.prior_result)
    output_path = resolve(repository, args.output, strict=False)
    raw_root = output_path.parent / "drumscribe-raw"
    raw_root.mkdir(parents=True, exist_ok=True)

    excluded_hashes = prior_audio_hashes(prior_result_path)
    records = select_records(prepared_path, excluded_hashes, args.records_per_category)
    expected = len(CATEGORY_ORDER) * args.records_per_category
    if len(records) != expected:
        raise RuntimeError(
            f"expected {expected} selected records; found {len(records)}"
        )

    configuration = StackedEnsembleConfig.load(config_path)
    checkpoint_paths = {
        name: resolve(repository, path) for name, path in CHECKPOINTS.items()
    }
    device = choose_device(args.device)
    with np.load(Path(records[0]["featurePath"]), allow_pickle=False) as arrays:
        mel_bands = int(arrays["features"].shape[1])
    models = load_models(
        configuration, checkpoint_paths, mel_bands=mel_bands, device=device
    )

    all_reference: list[list[Event]] = []
    all_prediction: list[list[Event]] = []
    grouped_reference: dict[str, list[list[Event]]] = defaultdict(list)
    grouped_prediction: dict[str, list[list[Event]]] = defaultdict(list)
    tracks: list[dict[str, Any]] = []
    durations: list[float] = []

    for sequence, record in enumerate(records, 1):
        audio_path = Path(record["audioPath"]).resolve(strict=True)
        annotation_path = Path(record["annotationPath"]).resolve(strict=True)
        feature_path = Path(record["featurePath"]).resolve(strict=True)
        scored_seconds = min(float(record["durationSeconds"]), args.window_seconds)
        reference = reference_events(annotation_path, scored_seconds)
        prediction = predict_drumscribe(
            feature_path, models, configuration, device, scored_seconds
        )
        category = str(record["category"])
        all_reference.append(reference)
        all_prediction.append(prediction)
        grouped_reference[category].append(reference)
        grouped_prediction[category].append(prediction)
        durations.append(scored_seconds)

        raw_path = raw_root / f"{sequence:03d}.json"
        raw_payload = {
            "schemaVersion": 1,
            "modelVersion": configuration.model_version,
            "sourceAudioSha256": sha256(audio_path),
            "scoredSeconds": scored_seconds,
            "events": [
                {"onsetSeconds": onset, "instrument": instrument}
                for onset, instrument in prediction
            ],
        }
        raw_path.write_text(
            json.dumps(raw_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        tracks.append(
            {
                "sequence": sequence,
                "trackId": str(record["trackId"]),
                "audioFile": audio_path.name,
                "audioSha256": sha256(audio_path),
                "style": str(record["style"]),
                "category": category,
                "sourceDurationSeconds": float(record["durationSeconds"]),
                "scoredSeconds": scored_seconds,
                "referenceEventCount": len(reference),
                "predictionEventCount": len(prediction),
                "scores": {
                    str(int(tolerance * 1000)): score_taxonomies(
                        reference, prediction, tolerance
                    )
                    for tolerance in TOLERANCES
                },
            }
        )
        print(
            json.dumps(
                {
                    "sequence": sequence,
                    "category": category,
                    "style": record["style"],
                    "audio": audio_path.name,
                }
            ),
            flush=True,
        )

    per_category = {
        category: {
            "recordCount": len(grouped_reference[category]),
            "shareOfBenchmark": len(grouped_reference[category]) / len(records),
            "scores": aggregate_scores(
                grouped_reference[category], grouped_prediction[category]
            ),
        }
        for category in CATEGORY_ORDER
    }
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Balanced 100-recording real human drum genre benchmark",
            "status": "opened_test_split_comparative_detector_benchmark",
            "recordCount": len(records),
            "recordsPerCategory": args.records_per_category,
            "windowSecondsMaximum": args.window_seconds,
            "totalScoredAudioSeconds": sum(durations),
            "rightsCleared": True,
            "license": "CC BY 4.0",
            "referenceSource": (
                "Google Magenta Groove MIDI Dataset aligned MIDI-derived events"
            ),
            "inputType": "isolated electronic-drum audio played by human drummers",
            "excludedPriorComparisonAudioSha256": sorted(excluded_hashes),
            "matcher": "one-to-one class-aware onset matching",
            "tolerancesMilliseconds": [int(value * 1000) for value in TOLERANCES],
            "limitations": [
                "This measures drum-event detection, not source separation from a full song.",
                "The recordings are human performances rendered by an electronic drum kit, not complete commercial recordings.",
                "The four categories are benchmark groupings derived from the dataset's style labels, not an exhaustive genre taxonomy.",
                "The selected recordings were excluded from the earlier ten-item live Drum2Notes comparison.",
                "The wider official Groove test split had already been opened during prior model research, so this is an exploratory comparative benchmark rather than a fresh sealed generalization estimate.",
                "This local repository is not a third-party audit environment.",
            ],
        },
        "system": {
            "name": "DrumScribe",
            "modelVersion": configuration.model_version,
            "configSha256": sha256(config_path),
            "checkpointSha256": {
                name: sha256(path) for name, path in sorted(checkpoint_paths.items())
            },
            "device": device,
        },
        "aggregate": aggregate_scores(all_reference, all_prediction),
        "categories": per_category,
        "tracks": tracks,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "output": str(output_path),
        "device": device,
        "records": len(records),
        "seconds": sum(durations),
        "detailedF1At50ms": report["aggregate"]["50"]["detailed14"]["micro"]["f1"],
        "familyF1At50ms": report["aggregate"]["50"]["family6"]["micro"]["f1"],
        "meanTrackDetailedF1At50ms": statistics.fmean(
            track["scores"]["50"]["detailed14"]["micro"]["f1"] for track in tracks
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
