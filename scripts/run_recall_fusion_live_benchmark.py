#!/usr/bin/env python3
"""Run the locked recall/fusion verification against live Drum2Notes.

Selection is frozen from the untouched GMD test split before either system is
run.  The deterministic seed deliberately gives broad style coverage, including
the only eligible progressive-rock performance, without consulting note labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
for source_root in (
    SCRIPTS_ROOT,
    REPOSITORY_ROOT / "packages" / "music-engine" / "src",
    REPOSITORY_ROOT / "ml" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from run_100_track_genre_benchmark import CATEGORY_ORDER, style_from_audio
from run_competitive_drum_benchmark import competitor_events, reference_events
from run_drum2notes_100_track_benchmark import write_json
from run_mdb_real_benchmark import _combine_event_lists, score
from run_novel_cross_genre_live_benchmark import (
    DEFAULT_ADTOF_EXECUTABLE,
    DEFAULT_ADTOF_PYTHON,
    DEFAULT_ADTOF_RUNNER,
    DEFAULT_DEMUCS_PYTHON,
    DEFAULT_PREPARED,
    benchmark_category,
    count_reference_events,
    make_clip,
    run_inference,
    score_results,
    sha256,
    verify_manifest_items,
)
from run_owner_approved_adtof_mdb import resolve

BENCHMARK_ID = "drumscribe-recall-fusion-holdout-v1"
DEFAULT_OUTPUT = Path("output/recall-fusion-holdout-v1-2026-09-05")
DEFAULT_RECALL_FUSION_RUNNER = Path(
    "scripts/model_runners/drumscribe_recall_fusion_runner.py"
)
WINDOW_SECONDS = 20.0
RECORDS_PER_CATEGORY = 5
SOURCE_SPLIT = "test"
DETAILED_CLASSES = {
    "KICK",
    "SNARE",
    "CROSS_STICK",
    "CLOSED_HIHAT",
    "OPEN_HIHAT",
    "PEDAL_HIHAT",
    "HIGH_TOM",
    "MID_TOM",
    "LOW_TOM",
    "FLOOR_TOM",
    "CRASH",
    "RIDE",
    "RIDE_BELL",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument("--adtof-runner", type=Path, default=DEFAULT_ADTOF_RUNNER)
    parser.add_argument(
        "--adtof-executable", type=Path, default=DEFAULT_ADTOF_EXECUTABLE
    )
    parser.add_argument(
        "--recall-fusion-runner", type=Path, default=DEFAULT_RECALL_FUSION_RUNNER
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    return parser.parse_args()


def selection_rank(value: str) -> str:
    return hashlib.sha256(f"{BENCHMARK_ID}:{value}".encode()).hexdigest()


def choose_records(prepared_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    candidates: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in payload["records"]:
        if record.get("split") != SOURCE_SPLIT:
            continue
        if float(record["durationSeconds"]) < WINDOW_SECONDS:
            continue
        style = style_from_audio(Path(record["audioPath"]))
        category = benchmark_category(style)
        candidates[category][style].append(record)

    selected: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        ranked_by_style = {
            style: sorted(
                records,
                key=lambda item: (
                    selection_rank(str(item["trackId"])),
                    str(item["trackId"]),
                ),
            )
            for style, records in candidates[category].items()
        }
        style_order = sorted(
            ranked_by_style,
            key=lambda style: (
                selection_rank(f"style:{category}:{style}"),
                style,
            ),
        )
        category_selection: list[dict[str, Any]] = []
        round_index = 0
        while len(category_selection) < RECORDS_PER_CATEGORY:
            added = False
            for style in style_order:
                records = ranked_by_style[style]
                if round_index < len(records):
                    category_selection.append(
                        {
                            **records[round_index],
                            "style": style,
                            "category": category,
                        }
                    )
                    added = True
                    if len(category_selection) == RECORDS_PER_CATEGORY:
                        break
            if not added:
                raise RuntimeError(f"not enough eligible records for {category}")
            round_index += 1
        selected.extend(category_selection)
    return selected


def prepare_manifest(prepared_path: Path, output_root: Path) -> dict[str, Any]:
    manifest_path = output_root / "selection-manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    if (output_root / "drumscribe-raw").exists() or (
        output_root / "drum2notes-raw"
    ).exists():
        raise RuntimeError("prediction output exists before selection was frozen")

    items: list[dict[str, Any]] = []
    for sequence, record in enumerate(choose_records(prepared_path), 1):
        source = Path(record["audioPath"]).resolve(strict=True)
        scored_seconds = min(WINDOW_SECONDS, float(record["durationSeconds"]))
        clip = output_root / "inputs" / f"{sequence:03d}.wav"
        make_clip(source, clip, scored_seconds)
        item = {
            "sequence": sequence,
            "trackId": str(record["trackId"]),
            "dataset": "groove",
            "inputKind": "real_human_drum_performance",
            "style": str(record["style"]),
            "category": str(record["category"]),
            "sourceSplit": SOURCE_SPLIT,
            "sourceAudioPath": str(source),
            "sourceAudioSha256": str(record["audioSha256"]),
            "annotationPath": str(Path(record["annotationPath"]).resolve()),
            "annotationSha256": sha256(Path(record["annotationPath"])),
            "audioPath": str(clip.resolve()),
            "audioSha256": sha256(clip),
            "scoredSeconds": scored_seconds,
        }
        item["referenceEventCount"] = count_reference_events(item)
        items.append(item)

    manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmarkId": BENCHMARK_ID,
        "selectionFrozenBeforeInference": True,
        "selectionUsesReferenceLabels": False,
        "sourceSplit": SOURCE_SPLIT,
        "windowSecondsMaximum": WINDOW_SECONDS,
        "items": items,
    }
    write_json(manifest_path, manifest)
    return manifest


def detailed_articulation_scores(
    items: list[dict[str, Any]], output_root: Path
) -> dict[str, Any]:
    references: list[list[tuple[float, str]]] = []
    drumscribe: list[list[tuple[float, str]]] = []
    drum2notes: list[list[tuple[float, str]]] = []
    for item in items:
        sequence = int(item["sequence"])
        limit = float(item["scoredSeconds"])
        references.append(
            [
                event
                for event in reference_events(Path(item["annotationPath"]), limit)
                if event[1] in DETAILED_CLASSES
            ]
        )
        payload = json.loads(
            (output_root / "drumscribe-raw" / f"{sequence:03d}.json").read_text(
                encoding="utf-8"
            )
        )
        drumscribe.append(
            sorted(
                (float(hit["onsetSeconds"]), str(hit["instrument"]))
                for hit in payload["hits"]
                if str(hit["instrument"]) in DETAILED_CLASSES
                and 0 <= float(hit["onsetSeconds"]) < limit
            )
        )
        music_path = output_root / "drum2notes-raw" / f"{sequence:03d}.music.json"
        detailed, _ = competitor_events(music_path, limit)
        drum2notes.append(
            [event for event in detailed if event[1] in DETAILED_CLASSES]
        )
    combined_reference = _combine_event_lists(references)
    return {
        system: {
            f"{milliseconds}ms": score(
                combined_reference,
                _combine_event_lists(predictions),
                milliseconds / 1_000,
            )
            for milliseconds in (20, 50, 100)
        }
        for system, predictions in (
            ("drumscribe", drumscribe),
            ("drum2notes", drum2notes),
        )
    }


def revise_report(
    report: dict[str, Any], items: list[dict[str, Any]], output_root: Path
) -> dict[str, Any]:
    first_prediction = json.loads(
        (output_root / "drumscribe-raw" / "001.json").read_text(encoding="utf-8")
    )
    report["benchmark"] = {
        "name": "Recall/fusion locked GMD test-split live comparison",
        "status": "frozen_same_audio_comparison_not_unseen_audit",
        "benchmarkId": BENCHMARK_ID,
        "selectionFrozenBeforeInference": True,
        "selectionUsesReferenceLabels": False,
        "sourceSplit": SOURCE_SPLIT,
        "itemCount": 20,
        "scoredSecondsPerItem": WINDOW_SECONDS,
        "tolerancesMs": [20, 50, 100],
        "limitations": [
            "A post-run provenance audit found that 17 of 20 source performances overlap older first-party experiments; this is not an organization-wide unseen set.",
            "GMD contains real human electronic-drum performances, not full commercial song mixtures.",
            "Drum2Notes is measured through its live public demo on the exact same PCM WAV bytes.",
        ],
    }
    report["categories"].pop("star_full_mix", None)
    report["systems"]["drumscribe"] = {
        "drumOnlyPipeline": (
            "first-party stacked articulation ensemble + ADTOF detector union + "
            "two-model consensus/periodic recovery"
        ),
        "modelVersion": str(first_prediction["modelVersion"]),
        "commercialRightsReference": "OWNER-ATTESTATION-2026-09-05",
        "productionProviderGatePassed": True,
    }
    report["articulationAggregate"] = detailed_articulation_scores(
        items, output_root
    )
    return report


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if args.prepare_only and args.score_only:
        raise ValueError("--prepare-only and --score-only are mutually exclusive")
    repository = args.repository.resolve(strict=True)
    prepared_path = resolve(repository, args.prepared)
    output_root = resolve(repository, args.output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = prepare_manifest(prepared_path, output_root)
    items = list(manifest["items"])
    verify_manifest_items(items)
    print(
        json.dumps(
            {
                "manifest": str(output_root / "selection-manifest.json"),
                "items": len(items),
                "manifestSha256": sha256(output_root / "selection-manifest.json"),
            }
        ),
        flush=True,
    )
    if args.prepare_only:
        return 0
    if not args.score_only:
        run_inference(repository, items, output_root, args)
    report = revise_report(score_results(items, output_root), items, output_root)
    result_path = output_root / "benchmark-result.json"
    write_json(result_path, report)
    print(
        json.dumps(
            {
                "output": str(result_path),
                "states": report["systems"]["drum2notes"]["resultStates"],
                "f1At50ms": {
                    system: round(scores["50ms"]["micro"]["f1"] * 100, 2)
                    for system, scores in report["aggregate"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
