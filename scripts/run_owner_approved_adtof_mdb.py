#!/usr/bin/env python3
"""Fresh end-to-end MDB run of the owner-approved Demucs -> ADTOF pipeline."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from drumscribe_music.licensing import require_production_safe
from drumscribe_music.providers.demucs import DemucsAdapter
from drumscribe_music.providers.external import ADTOFResearchTranscriptionProvider
from run_competitive_drum_benchmark import sha256
from run_mdb_real_benchmark import (
    MDB_INSTRUMENT_TO_FAMILY,
    TEST_TRACKS,
    _combine_event_lists,
    _reference_events,
    score,
)

APPROVAL_REFERENCE = "OWNER-ATTESTATION-2026-09-05"
DEFAULT_DATASET = Path("data/research-corpus/MDBDrums/MDB Drums")
DEFAULT_OUTPUT = Path("output/mdb-owner-approved-adtof-rerun-2026-09-05")
DEFAULT_DEMUCS_PYTHON = Path("apps/api/.venv/bin/python")
DEFAULT_ADTOF_PYTHON = Path(".research-models/adtof-env/bin/python")
DEFAULT_ADTOF_RUNNER = Path("scripts/model_runners/adtof_runner.py")
DEFAULT_ADTOF_EXECUTABLE = Path(".research-models/adtof-env/bin/adtof")
TOLERANCES_MS = (20, 50, 100)

Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument("--adtof-runner", type=Path, default=DEFAULT_ADTOF_RUNNER)
    parser.add_argument(
        "--adtof-executable", type=Path, default=DEFAULT_ADTOF_EXECUTABLE
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def resolve_executable(repository: Path, path: Path) -> Path:
    """Return an absolute executable path without dereferencing venv symlinks."""

    candidate = path if path.is_absolute() else repository / path
    candidate = candidate.absolute()
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def prediction_events(payload: dict[str, Any]) -> list[Event]:
    events: list[Event] = []
    for hit in payload.get("hits", []):
        family = MDB_INSTRUMENT_TO_FAMILY.get(str(hit.get("instrument", "")))
        if family:
            events.append((float(hit["onsetSeconds"]), family))
    return sorted(events)


def scores(reference: list[Event], prediction: list[Event]) -> dict[str, Any]:
    return {
        f"{milliseconds}ms": score(reference, prediction, milliseconds / 1000)
        for milliseconds in TOLERANCES_MS
    }


def main() -> int:
    args = parse_args()
    repository = args.repository.resolve(strict=True)
    dataset = resolve(repository, args.dataset)
    output_root = resolve(repository, args.output, strict=False)
    prediction_root = output_root / "predictions"
    prediction_root.mkdir(parents=True, exist_ok=True)

    demucs_python = resolve_executable(repository, args.demucs_python)
    adtof_python = resolve_executable(repository, args.adtof_python)
    adtof_runner = resolve(repository, args.adtof_runner)
    adtof_executable = resolve_executable(repository, args.adtof_executable)
    separation = DemucsAdapter(
        model="htdemucs_ft", python_executable=str(demucs_python)
    )
    transcription = ADTOFResearchTranscriptionProvider(
        (
            str(adtof_python),
            str(adtof_runner),
            "--executable",
            str(adtof_executable),
            "--device",
            args.device,
        ),
        model_version="adtof-pytorch-85c192e78f71",
        timeout_seconds=3_600,
    )
    require_production_safe(separation, production=True)
    require_production_safe(transcription, production=True)

    annotation_root = dataset / "annotations" / "class"
    mixture_root = dataset / "audio" / "full_mix"
    all_references: list[list[Event]] = []
    all_predictions: list[list[Event]] = []
    rows: list[dict[str, Any]] = []

    for index, track in enumerate(TEST_TRACKS, 1):
        started = time.monotonic()
        mixture = mixture_root / f"{track}_MIX.wav"
        annotation = annotation_root / f"{track}_class.txt"
        prediction_path = prediction_root / f"{track}.json"

        if prediction_path.exists() and not args.force:
            payload = json.loads(prediction_path.read_text(encoding="utf-8"))
            stem_hash = str(payload["source"]["drumStemSha256"])
            mode = "resumed"
        else:
            with tempfile.TemporaryDirectory(
                prefix="drumscribe-owner-approved-mdb-"
            ) as directory:
                stem = Path(directory) / "drums.wav"
                separation.separate_drums(mixture, stem)
                stem_hash = sha256(stem)
                hits = transcription.transcribe(stem)
            payload = {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
                "modelVersion": transcription.version,
                "commercialRightsReference": APPROVAL_REFERENCE,
                "source": {
                    "fullMixSha256": sha256(mixture),
                    "drumStemSha256": stem_hash,
                    "separationProvider": separation.provider_id,
                    "separationModel": separation.version,
                },
                "hits": [
                    {
                        "instrument": hit.instrument_class.value,
                        "onsetSeconds": hit.onset_seconds,
                        "velocity": hit.velocity,
                        "confidence": hit.confidence,
                    }
                    for hit in hits
                ],
            }
            write_json(prediction_path, payload)
            mode = "fresh"

        reference = _reference_events(annotation)
        prediction = prediction_events(payload)
        track_scores = scores(reference, prediction)
        all_references.append(reference)
        all_predictions.append(prediction)
        rows.append(
            {
                "track": track,
                "mode": mode,
                "referenceEvents": len(reference),
                "predictedEvents": len(prediction),
                "referenceClassCounts": dict(Counter(label for _, label in reference)),
                "predictionClassCounts": dict(
                    Counter(label for _, label in prediction)
                ),
                "scores": track_scores,
                "processingSeconds": round(time.monotonic() - started, 3),
                "hashes": {
                    "fullMix": sha256(mixture),
                    "drumStem": stem_hash,
                    "reference": sha256(annotation),
                    "prediction": sha256(prediction_path),
                },
            }
        )
        print(
            json.dumps(
                {
                    "completed": index,
                    "total": len(TEST_TRACKS),
                    "track": track,
                    "mode": mode,
                    "f1At50ms": track_scores["50ms"]["micro"]["f1"],
                }
            ),
            flush=True,
        )

    combined_reference = _combine_event_lists(all_references)
    combined_prediction = _combine_event_lists(all_predictions)
    aggregate = scores(combined_reference, combined_prediction)
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "MDB Drums fresh owner-approved commercial pipeline rerun",
            "split": "MIREX test",
            "trackCount": len(TEST_TRACKS),
            "inputType": "real human performances in full-band mixtures",
            "datasetLicense": "CC BY-NC-SA 4.0",
            "benchmarkResearchOnly": True,
            "predictionsGeneratedFreshFromFullMixtures": True,
            "testReferencesUsedForTrainingOrCalibration": False,
            "matcher": "class-aware one-to-one onset matching",
            "tolerancesMilliseconds": list(TOLERANCES_MS),
        },
        "system": {
            "pipeline": "htdemucs_ft -> ADTOF-pytorch",
            "commercialRightsReference": APPROVAL_REFERENCE,
            "productionProviderGatePassed": True,
            "separationProvider": separation.provider_id,
            "transcriptionProvider": transcription.provider_id,
        },
        "aggregate": aggregate,
        "tracks": rows,
    }
    destination = output_root / "benchmark-result.json"
    write_json(destination, report)
    print(
        json.dumps(
            {
                "output": str(destination),
                "f1At50ms": aggregate["50ms"]["micro"]["f1"],
                "precisionAt50ms": aggregate["50ms"]["micro"]["precision"],
                "recallAt50ms": aggregate["50ms"]["micro"]["recall"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
