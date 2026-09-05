#!/usr/bin/env python3
"""Run the first frozen IDMT acoustic-drum comparison against Drum2Notes.

The benchmark uses every polyphonic RealDrum mixture in IDMT-SMT-Drums V2.
Selection and source hashes are written before either system is run, and the
SVL reference labels are not parsed until inference for both systems finishes.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
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

from run_competitive_drum_benchmark import CORE_THREE_MAP, competitor_events
from run_drum2notes_100_track_benchmark import write_json
from run_mdb_real_benchmark import _combine_event_lists, score
from run_novel_cross_genre_live_benchmark import (
    DEFAULT_ADTOF_PYTHON,
    DEFAULT_DEMUCS_PYTHON,
    run_inference,
    sha256,
    verify_manifest_items,
)
from run_owner_approved_adtof_mdb import resolve

BENCHMARK_ID = "idmt-realdrum-sealed-live-v1"
DEFAULT_CORPUS = Path(
    "data/research-corpus/idmt-smt-drums-v2/extracted"
)
DEFAULT_OUTPUT = Path("output/idmt-realdrum-sealed-live-v1-2026-09-05")
DEFAULT_RECALL_FUSION_RUNNER = Path(
    "scripts/model_runners/drumscribe_recall_fusion_runner.py"
)
EXPECTED_RECORD_COUNT = 14
TOLERANCES_MS = (20, 50, 100)
REFERENCE_SUFFIXES = {
    "KD": "KICK",
    "SD": "SNARE",
    "HH": "HIHAT",
}
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument(
        "--recall-fusion-runner", type=Path, default=DEFAULT_RECALL_FUSION_RUNNER
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--drum-only-profile",
        choices=("electronic", "acoustic"),
        default="acoustic",
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument(
        "--opened-iteration",
        action="store_true",
        help="Mark a post-baseline run whose model choices used the opened corpus.",
    )
    return parser.parse_args()


def discover_records(corpus_root: Path) -> list[dict[str, Any]]:
    """Select acoustic mixtures using filenames only, without opening labels."""
    audio_root = corpus_root / "audio"
    annotation_root = corpus_root / "annotation_svl"
    records: list[dict[str, Any]] = []
    for audio in sorted(audio_root.glob("RealDrum*#MIX.wav")):
        track_id = audio.name.removesuffix("#MIX.wav")
        annotations = {
            suffix: annotation_root / f"{track_id}#{suffix}.svl"
            for suffix in REFERENCE_SUFFIXES
        }
        missing = [path for path in annotations.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"missing annotations for {track_id}: {missing}")
        records.append(
            {
                "trackId": track_id,
                "audioPath": str(audio.resolve(strict=True)),
                "annotationPaths": {
                    suffix: str(path.resolve(strict=True))
                    for suffix, path in annotations.items()
                },
            }
        )
    if len(records) != EXPECTED_RECORD_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_RECORD_COUNT} RealDrum mixtures; found {len(records)}"
        )
    return records


def prepare_manifest(
    corpus_root: Path, output_root: Path, *, opened_iteration: bool = False
) -> dict[str, Any]:
    manifest_path = output_root / "selection-manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    if (output_root / "drumscribe-raw").exists() or (
        output_root / "drum2notes-raw"
    ).exists():
        raise RuntimeError("prediction output exists before selection was frozen")

    items: list[dict[str, Any]] = []
    for sequence, record in enumerate(discover_records(corpus_root), 1):
        audio = Path(record["audioPath"])
        annotation_paths = {
            suffix: Path(path)
            for suffix, path in record["annotationPaths"].items()
        }
        items.append(
            {
                "sequence": sequence,
                "trackId": record["trackId"],
                "dataset": "idmt_smt_drums_v2",
                "inputKind": "real_acoustic_drum_performance",
                "style": "acoustic_drum_loop",
                "category": "idmt_realdrum",
                "sourceSplit": "published_realdrum_collection",
                "sourceAudioPath": str(audio),
                "audioPath": str(audio),
                "audioSha256": sha256(audio),
                "annotationPath": str(annotation_paths["KD"]),
                "annotationPaths": {
                    suffix: str(path) for suffix, path in annotation_paths.items()
                },
                "annotationSha256": sha256(annotation_paths["KD"]),
                "annotationSha256s": {
                    suffix: sha256(path) for suffix, path in annotation_paths.items()
                },
                "scoredSeconds": audio_duration(audio),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmarkId": (
            f"{BENCHMARK_ID}-acoustic-profile-v2"
            if opened_iteration
            else BENCHMARK_ID
        ),
        "selectionFrozenBeforeInference": True,
        "selectionUsesReferenceLabels": False,
        "selectionRule": "all 14 IDMT RealDrum polyphonic MIX files in filename order",
        "sourceArchiveMd5": "d2664b4c2aaa34b90ba2f57b389c5663",
        "evaluationStatus": (
            "opened_model_iteration" if opened_iteration else "independent_first_run"
        ),
        "items": items,
    }
    write_json(manifest_path, manifest)
    return manifest


def audio_duration(path: Path) -> float:
    import wave

    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def verify_idmt_items(items: list[dict[str, Any]]) -> None:
    verify_manifest_items(items)
    for item in items:
        for suffix, value in item["annotationPaths"].items():
            annotation = Path(value).resolve(strict=True)
            if sha256(annotation) != item["annotationSha256s"][suffix]:
                raise RuntimeError(f"benchmark annotation changed: {annotation}")


def parse_svl(path: Path, label: str, limit: float) -> list[Event]:
    root = ET.parse(path).getroot()
    model = root.find("./data/model")
    if model is None:
        raise ValueError(f"SVL has no model: {path}")
    sample_rate = float(model.attrib["sampleRate"])
    if sample_rate <= 0:
        raise ValueError(f"invalid SVL sample rate: {sample_rate}")
    dataset = root.find("./data/dataset")
    if dataset is None:
        return []
    return sorted(
        (onset, label)
        for point in dataset.findall("point")
        if 0 <= (onset := float(point.attrib["frame"]) / sample_rate) < limit
    )


def reference_events(item: dict[str, Any]) -> list[Event]:
    limit = float(item["scoredSeconds"])
    return sorted(
        event
        for suffix, label in REFERENCE_SUFFIXES.items()
        for event in parse_svl(Path(item["annotationPaths"][suffix]), label, limit)
    )


def drumscribe_events(path: Path, limit: float) -> list[Event]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sorted(
        (float(hit["onsetSeconds"]), CORE_THREE_MAP[instrument])
        for hit in payload["hits"]
        if (instrument := str(hit["instrument"])) in CORE_THREE_MAP
        and 0 <= float(hit["onsetSeconds"]) < limit
    )


def drum2notes_events(path: Path, limit: float) -> tuple[list[Event], float]:
    detailed, bpm = competitor_events(path, limit)
    return (
        sorted(
            (onset, CORE_THREE_MAP[instrument])
            for onset, instrument in detailed
            if instrument in CORE_THREE_MAP
        ),
        bpm,
    )


def aggregate(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    combined_reference = _combine_event_lists(references)
    combined_prediction = _combine_event_lists(predictions)
    return {
        f"{milliseconds}ms": score(
            combined_reference, combined_prediction, milliseconds / 1_000
        )
        for milliseconds in TOLERANCES_MS
    }


def score_results(
    items: list[dict[str, Any]],
    output_root: Path,
    *,
    evaluation_status: str = "independent_first_run",
    drum_only_profile: str = "electronic",
) -> dict[str, Any]:
    references: list[list[Event]] = []
    drumscribe_predictions: list[list[Event]] = []
    drum2notes_predictions: list[list[Event]] = []
    states: Counter[str] = Counter()
    tracks: list[dict[str, Any]] = []
    first_prediction = json.loads(
        (output_root / "drumscribe-raw" / "001.json").read_text(encoding="utf-8")
    )
    model_version = str(first_prediction["modelVersion"])

    for item in items:
        sequence = int(item["sequence"])
        stem = f"{sequence:03d}"
        limit = float(item["scoredSeconds"])
        reference = reference_events(item)
        drumscribe_path = output_root / "drumscribe-raw" / f"{stem}.json"
        drumscribe = drumscribe_events(drumscribe_path, limit)
        job_path = output_root / "drum2notes-raw" / f"{stem}.job.json"
        music_path = output_root / "drum2notes-raw" / f"{stem}.music.json"
        job = (
            json.loads(job_path.read_text(encoding="utf-8"))
            if job_path.exists()
            else {"state": "missing"}
        )
        state = str(job.get("state", "missing"))
        states[state] += 1
        drum2notes: list[Event] = []
        estimated_bpm: float | None = None
        if state == "ok" and music_path.exists():
            drum2notes, estimated_bpm = drum2notes_events(music_path, limit)

        references.append(reference)
        drumscribe_predictions.append(drumscribe)
        drum2notes_predictions.append(drum2notes)
        tracks.append(
            {
                "sequence": sequence,
                "trackId": item["trackId"],
                "audioSha256": item["audioSha256"],
                "scoredSeconds": limit,
                "drum2notesState": state,
                "drum2notesJobId": job.get("id"),
                "drum2notesEstimatedBpm": estimated_bpm,
                "eventCounts": {
                    "reference": len(reference),
                    "drumscribe": len(drumscribe),
                    "drum2notes": len(drum2notes),
                },
                "scores": {
                    f"{milliseconds}ms": {
                        "drumscribe": score(
                            reference, drumscribe, milliseconds / 1_000
                        ),
                        "drum2notes": score(
                            reference, drum2notes, milliseconds / 1_000
                        ),
                    }
                    for milliseconds in TOLERANCES_MS
                },
                "hashes": {
                    "drumscribePrediction": sha256(drumscribe_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.exists()
                    else None,
                },
            }
        )

    manifest_path = output_root / "selection-manifest.json"
    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": (
                "IDMT RealDrum first-run frozen live comparison"
                if evaluation_status == "independent_first_run"
                else "IDMT RealDrum opened acoustic-profile v2 comparison"
            ),
            "status": evaluation_status,
            "benchmarkId": BENCHMARK_ID,
            "recordCount": len(items),
            "totalScoredAudioSeconds": sum(
                float(item["scoredSeconds"]) for item in items
            ),
            "primaryMetric": "three-family class-aware micro F1 at 50ms",
            "families": ["KICK", "SNARE", "HIHAT"],
            "sameAudioBytesForBothSystems": True,
            "selectionFrozenBeforeInference": True,
            "selectionUsedReferenceLabels": False,
            "selectionManifestSha256": sha256(manifest_path),
            "researchOnly": True,
            "independentModelEvaluation": evaluation_status == "independent_first_run",
            "limitations": [
                (
                    "The corpus was new to this repository before the first run, but becomes opened test data after that result."
                    if evaluation_status == "independent_first_run"
                    else "This is an opened-corpus improvement measurement; model/profile choices used the earlier IDMT result and require external confirmation."
                ),
                "IDMT RealDrum contains acoustic drum-kit loops rather than complete music mixtures.",
                "Only kick, snare, and hi-hat have reference annotations, so tom and cymbal accuracy is not measured here.",
                "Fraunhofer publishes IDMT-SMT-Drums V2 for evaluation under CC BY-NC-ND 4.0; files are used only for local research and are not redistributed.",
                "Drum2Notes is measured through its live public demo on the exact same WAV bytes.",
            ],
        },
        "systems": {
            "drumscribe": {
                "pipeline": f"{model_version} {drum_only_profile} drum-only route",
                "modelVersion": model_version,
                "drumOnlyProfile": drum_only_profile,
                "commercialRightsReference": "OWNER-ATTESTATION-2026-09-05",
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes",
                "surface": "live public demo",
                "modelSetting": "solo / all drum notes",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribe": aggregate(references, drumscribe_predictions),
            "drum2notes": aggregate(references, drum2notes_predictions),
        },
        "tracks": tracks,
    }


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if args.prepare_only and args.score_only:
        raise ValueError("--prepare-only and --score-only are mutually exclusive")
    repository = args.repository.resolve(strict=True)
    corpus_root = resolve(repository, args.corpus)
    output_root = resolve(repository, args.output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = prepare_manifest(
        corpus_root, output_root, opened_iteration=args.opened_iteration
    )
    items = list(manifest["items"])
    verify_idmt_items(items)
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
    report = score_results(
        items,
        output_root,
        evaluation_status=str(
            manifest.get("evaluationStatus", "independent_first_run")
        ),
        drum_only_profile=args.drum_only_profile,
    )
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
