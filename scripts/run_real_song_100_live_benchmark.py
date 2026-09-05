#!/usr/bin/env python3
"""Compare production DrumScribe v3 and live Drum2Notes on 100 song excerpts.

The frozen suite combines all 89 available drum-containing RWC Popular clips
with the 11-song MDB Drums MIREX test partition.  Every item is a 20-second
full musical mixture with an aligned drum reference.  Both systems receive the
same audio bytes.  The licensed datasets make this a local, research-only,
opened development comparison rather than an independent product claim.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from drumscribe_music.licensing import require_production_safe
from drumscribe_music.providers.external import (
    DrumScribeRecallFusionTranscriptionProvider,
)
from run_competitive_drum_benchmark import competitor_events, sha256
from run_drum2notes_100_track_benchmark import API_ROOT, poll, request_bytes, write_json
from run_mdb_real_benchmark import (
    INSTRUMENT_TO_FAMILY,
    TEST_TRACKS,
    _combine_event_lists,
    _reference_events,
    score,
)
from run_owner_approved_adtof_mdb import resolve, resolve_executable
from run_owner_approved_drum2notes_mdb_comparison import (
    APPROVAL_REFERENCE,
    TEST_GENRES,
)

DEFAULT_RWC_ROOTS = (
    Path("data/research-corpus/rwc-popular-50-v1"),
    Path("data/research-corpus/rwc-popular-holdout-39-v1"),
)
DEFAULT_MDB_DATASET = Path("data/research-corpus/MDBDrums/MDB Drums")
DEFAULT_MDB_SOURCE = Path("output/mdb-real-test11-inputs")
DEFAULT_MDB_STEM_EVIDENCE = Path("output/mdb-recall-fusion-v3-live-test11-2026-09-06")
DEFAULT_OUTPUT = Path("output/real-song-100-v3-vs-drum2notes-2026-09-06")
DEFAULT_COMPACT_OUTPUT = Path(
    "docs/benchmarks/data/REAL_SONG_100_V3_VS_DRUM2NOTES.json"
)
DEFAULT_ADTOF_PYTHON = Path(".research-models/adtof-env/bin/python")
DEFAULT_RUNNER = Path("scripts/model_runners/drumscribe_recall_fusion_runner.py")
MODEL_VERSION = "drumscribe-recall-fusion-v3"
WINDOW_SECONDS = 20.0
TOLERANCES_MS = (20, 50, 100)
FAMILY5 = frozenset(("KICK", "SNARE", "HIHAT", "TOM", "CYMBAL"))
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--rwc-root", type=Path, action="append", default=[])
    parser.add_argument("--mdb-dataset", type=Path, default=DEFAULT_MDB_DATASET)
    parser.add_argument("--mdb-source", type=Path, default=DEFAULT_MDB_SOURCE)
    parser.add_argument(
        "--mdb-stem-evidence", type=Path, default=DEFAULT_MDB_STEM_EVIDENCE
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--compact-output", type=Path, default=DEFAULT_COMPACT_OUTPUT)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--device", choices=("cpu", "cuda", "mps"), default="cpu")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--score-only", action="store_true")
    return parser.parse_args()


def _family5(events: list[Event]) -> list[Event]:
    """Map detailed events to five common families and remove exact unisons."""
    mapped = {
        (round(float(onset), 6), family)
        for onset, instrument in events
        if (family := INSTRUMENT_TO_FAMILY.get(str(instrument))) in FAMILY5
        and 0 <= float(onset) < WINDOW_SECONDS
    }
    return sorted(mapped)


def _prediction_family5(payload: dict[str, Any]) -> list[Event]:
    events = [
        (float(hit["onsetSeconds"]), str(hit["instrument"]))
        for hit in payload.get("hits", [])
    ]
    return _family5(events)


def _competitor_family5(path: Path) -> tuple[list[Event], float]:
    events, bpm = competitor_events(path, WINDOW_SECONDS)
    return _family5(events), bpm


def _scores(reference: list[Event], prediction: list[Event]) -> dict[str, Any]:
    return {
        f"{milliseconds}ms": score(reference, prediction, milliseconds / 1_000)
        for milliseconds in TOLERANCES_MS
    }


def _aggregate(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    return _scores(_combine_event_lists(references), _combine_event_lists(predictions))


def _validate_rwc_root(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selection_path = (root / "selection-manifest.json").resolve(strict=True)
    separation_path = (root / "separation-manifest.json").resolve(strict=True)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    separation = json.loads(separation_path.read_text(encoding="utf-8"))
    if selection.get("status") != "selection_and_references_frozen_before_inference":
        raise RuntimeError(f"RWC selection is not frozen: {selection_path}")
    if separation.get("sourceSelectionManifestSha256") != sha256(selection_path):
        raise RuntimeError(f"RWC separation does not match selection: {root}")
    if separation.get("model") != "htdemucs_ft":
        raise RuntimeError(f"unexpected RWC separation model: {root}")
    return selection, separation


def load_records(
    repository: Path,
    rwc_roots: list[Path],
    mdb_dataset: Path,
    mdb_source: Path,
    mdb_stem_evidence: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_audio: set[str] = set()

    for unresolved_root in rwc_roots:
        root = resolve(repository, unresolved_root)
        selection, separation = _validate_rwc_root(root)
        stems = {str(row["rwcId"]): row for row in separation["stems"]}
        for track in selection["tracks"]:
            track_id = str(track["rwcId"])
            clip = (root / str(track["clipRelativePath"])).resolve(strict=True)
            stem_info = stems.get(track_id)
            if stem_info is None:
                raise RuntimeError(f"missing RWC separated stem: {track_id}")
            stem = (root / str(stem_info["drumsRelativePath"])).resolve(strict=True)
            clip_hash = sha256(clip)
            if clip_hash != track["clipSha256"]:
                raise RuntimeError(f"RWC clip hash changed: {track_id}")
            if stem_info["sourceClipSha256"] != clip_hash:
                raise RuntimeError(f"RWC stem source changed: {track_id}")
            if sha256(stem) != stem_info["drumsSha256"]:
                raise RuntimeError(f"RWC stem hash changed: {track_id}")
            reference = _family5(
                [
                    (float(event["onsetSeconds"]), str(event["instrument"]))
                    for event in track["referenceEvents"]
                ]
            )
            records.append(
                {
                    "recordId": f"rwc:{track_id}",
                    "dataset": "RWC Popular",
                    "title": str(track["title"]),
                    "genre": str(track["genreSub"]),
                    "performanceType": str(track["drumType"]),
                    "audioPath": clip,
                    "audioSha256": clip_hash,
                    "stemPath": stem,
                    "stemSha256": str(stem_info["drumsSha256"]),
                    "reference": reference,
                    "referenceSha256": str(track["referenceMidiSha256"]),
                }
            )

    evidence_report = json.loads(
        (mdb_stem_evidence / "benchmark-result.json").read_text(encoding="utf-8")
    )
    evidence_by_track = {str(row["track"]): row for row in evidence_report["tracks"]}
    for track_id in TEST_TRACKS:
        clip = (mdb_source / "competitor-upload-20s" / f"{track_id}_20s.wav").resolve(
            strict=True
        )
        stem = (mdb_stem_evidence / "drum-stems" / f"{track_id}_drums.wav").resolve(
            strict=True
        )
        annotation = (
            mdb_dataset / "annotations" / "class" / f"{track_id}_class.txt"
        ).resolve(strict=True)
        evidence = evidence_by_track[track_id]
        clip_hash = sha256(clip)
        if clip_hash != evidence["hashes"]["fullMixExcerpt"]:
            raise RuntimeError(f"MDB clip hash changed: {track_id}")
        if sha256(stem) != evidence["hashes"]["drumStem"]:
            raise RuntimeError(f"MDB stem hash changed: {track_id}")
        reference = sorted(
            {
                (round(float(onset), 6), family)
                for onset, family in _reference_events(annotation)
                if family in FAMILY5 and 0 <= float(onset) < WINDOW_SECONDS
            }
        )
        records.append(
            {
                "recordId": f"mdb:{track_id}",
                "dataset": "MDB Drums",
                "title": track_id,
                "genre": TEST_GENRES[track_id],
                "performanceType": "live",
                "audioPath": clip,
                "audioSha256": clip_hash,
                "stemPath": stem,
                "stemSha256": sha256(stem),
                "reference": reference,
                "referenceSha256": sha256(annotation),
            }
        )

    for sequence, record in enumerate(records, 1):
        record["sequence"] = sequence
        record_id = str(record["recordId"])
        audio_hash = str(record["audioSha256"])
        if record_id in seen_ids or audio_hash in seen_audio:
            raise RuntimeError(f"duplicate benchmark item: {record_id}")
        if not record["reference"]:
            raise RuntimeError(f"empty benchmark reference: {record_id}")
        seen_ids.add(record_id)
        seen_audio.add(audio_hash)
    if len(records) != 100:
        raise RuntimeError(f"expected exactly 100 song excerpts; found {len(records)}")
    return records


def _submit_competitor(audio_path: Path, sequence: int) -> str:
    params = {
        "settings": {
            "instruments": ["drums"],
            "min_duration": 0.0625,
            "triplets": True,
            "sections": False,
            "model": "solo",
            "drums": {"drum_notes": "all"},
        },
        "apriori": {
            "title": f"DrumScribe real-song benchmark {sequence:03d}",
            "composer": "Licensed research corpus",
            "agreedToTerms": True,
        },
    }
    completed = subprocess.run(
        [
            "curl",
            "-fsS",
            "--retry",
            "3",
            "--retry-all-errors",
            "--max-time",
            "120",
            "-X",
            "POST",
            f"{API_ROOT}/upload",
            "-F",
            f"file=@{audio_path}",
            "--form-string",
            "usecredits=false",
            "--form-string",
            "usetickets=false",
            "--form-string",
            "source=file",
            "--form-string",
            "type=drum2notes",
            "--form-string",
            f"params={json.dumps(params, separators=(',', ':'))}",
            "--form-string",
            f"title=DrumScribe real-song benchmark {sequence:03d}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=150,
    )
    payload = json.loads(completed.stdout)
    job_id = str(payload.get("jobId", ""))
    if not job_id:
        raise RuntimeError(f"upload returned no jobId: {payload}")
    return job_id


def _process_competitor(
    record: dict[str, Any],
    raw_root: Path,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    sequence = int(record["sequence"])
    stem = f"{sequence:03d}"
    job_path = raw_root / f"{stem}.job.json"
    music_path = raw_root / f"{stem}.music.json"
    job_id = ""
    if job_path.exists():
        retained = json.loads(job_path.read_text(encoding="utf-8"))
        if retained.get("sourceAudioSha256") != record["audioSha256"]:
            raise RuntimeError(f"stale Drum2Notes output: {job_path}")
        if retained.get("state") == "ok" and music_path.exists():
            return retained
        job_id = str(retained.get("id") or retained.get("jobId") or "")
    try:
        if not job_id:
            job_id = _submit_competitor(Path(record["audioPath"]), sequence)
            write_json(
                job_path,
                {
                    "id": job_id,
                    "state": "submitted",
                    "sequence": sequence,
                    "recordId": record["recordId"],
                    "sourceAudioSha256": record["audioSha256"],
                },
            )
        payload = poll(job_id, poll_seconds, timeout_seconds)
        retained = {
            **payload,
            "id": job_id,
            "sequence": sequence,
            "recordId": record["recordId"],
            "sourceAudioSha256": record["audioSha256"],
        }
        write_json(job_path, retained)
        if payload.get("state") == "ok":
            music_path.write_bytes(request_bytes(f"{API_ROOT}/musj?id={job_id}"))
        return retained
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        retained = {
            "id": job_id or None,
            "state": "runner_error",
            "sequence": sequence,
            "recordId": record["recordId"],
            "sourceAudioSha256": record["audioSha256"],
            "runnerError": f"{type(error).__name__}: {error}",
        }
        write_json(job_path, retained)
        return retained


def run_predictions(
    records: list[dict[str, Any]],
    repository: Path,
    output_root: Path,
    args: argparse.Namespace,
) -> None:
    competitor_root = output_root / "drum2notes-raw"
    drumscribe_root = output_root / "drumscribe-raw"
    competitor_root.mkdir(parents=True, exist_ok=True)
    drumscribe_root.mkdir(parents=True, exist_ok=True)
    transcription = DrumScribeRecallFusionTranscriptionProvider(
        (
            str(resolve_executable(repository, args.adtof_python)),
            str(resolve(repository, args.runner)),
            "--repository",
            str(repository),
            "--device",
            args.device,
        ),
        model_version=MODEL_VERSION,
        timeout_seconds=3_600,
    )
    require_production_safe(transcription, production=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                _process_competitor,
                record,
                competitor_root,
                args.poll_seconds,
                args.timeout_seconds,
            ): int(record["sequence"])
            for record in records
        }
        for completed, record in enumerate(records, 1):
            sequence = int(record["sequence"])
            destination = drumscribe_root / f"{sequence:03d}.json"
            if destination.exists():
                retained = json.loads(destination.read_text(encoding="utf-8"))
                if (
                    retained.get("source", {}).get("fullMixSha256")
                    == record["audioSha256"]
                ):
                    print(
                        json.dumps(
                            {
                                "system": "drumscribe",
                                "completed": completed,
                                "total": 100,
                                "sequence": sequence,
                                "state": "cached",
                            }
                        ),
                        flush=True,
                    )
                    continue
                raise RuntimeError(f"stale DrumScribe output: {destination}")
            hits = transcription.transcribe_multiview(
                Path(record["audioPath"]), Path(record["stemPath"])
            )
            write_json(
                destination,
                {
                    "schemaVersion": 1,
                    "provider": transcription.provider_id,
                    "modelVersion": transcription.version,
                    "source": {
                        "fullMixSha256": record["audioSha256"],
                        "drumStemSha256": record["stemSha256"],
                        "separationModel": "htdemucs_ft",
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
                },
            )
            print(
                json.dumps(
                    {
                        "system": "drumscribe",
                        "completed": completed,
                        "total": 100,
                        "sequence": sequence,
                        "hits": len(hits),
                    }
                ),
                flush=True,
            )

        for completed, future in enumerate(as_completed(futures), 1):
            result = future.result()
            print(
                json.dumps(
                    {
                        "system": "drum2notes",
                        "completed": completed,
                        "total": 100,
                        "sequence": futures[future],
                        "state": result.get("state"),
                    }
                ),
                flush=True,
            )


def _group_scores(
    records: list[dict[str, Any]],
    references: list[list[Event]],
    drumscribe: list[list[Event]],
    drum2notes: list[list[Event]],
    key: str,
) -> dict[str, Any]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[str(record[key])].append(index)
    return {
        value: {
            "recordCount": len(indices),
            "drumscribe": _aggregate(
                [references[index] for index in indices],
                [drumscribe[index] for index in indices],
            ),
            "drum2notes": _aggregate(
                [references[index] for index in indices],
                [drum2notes[index] for index in indices],
            ),
        }
        for value, indices in sorted(grouped.items())
    }


def build_report(
    records: list[dict[str, Any]], output_root: Path, processing_seconds: float | None
) -> dict[str, Any]:
    references: list[list[Event]] = []
    drumscribe_predictions: list[list[Event]] = []
    competitor_predictions: list[list[Event]] = []
    rows: list[dict[str, Any]] = []
    states: Counter[str] = Counter()
    wins = Counter()

    for record in records:
        sequence = int(record["sequence"])
        prediction_path = output_root / "drumscribe-raw" / f"{sequence:03d}.json"
        job_path = output_root / "drum2notes-raw" / f"{sequence:03d}.job.json"
        music_path = output_root / "drum2notes-raw" / f"{sequence:03d}.music.json"
        prediction_payload = json.loads(prediction_path.read_text(encoding="utf-8"))
        job = (
            json.loads(job_path.read_text(encoding="utf-8"))
            if job_path.exists()
            else {"state": "missing"}
        )
        if (
            prediction_payload.get("source", {}).get("fullMixSha256")
            != record["audioSha256"]
        ):
            raise RuntimeError(f"DrumScribe input hash mismatch: {record['recordId']}")
        if job.get("sourceAudioSha256") != record["audioSha256"]:
            raise RuntimeError(f"Drum2Notes input hash mismatch: {record['recordId']}")
        state = str(job.get("state", "missing"))
        states[state] += 1
        reference = list(record["reference"])
        drumscribe = _prediction_family5(prediction_payload)
        competitor: list[Event] = []
        competitor_bpm: float | None = None
        if state == "ok" and music_path.exists():
            competitor, competitor_bpm = _competitor_family5(music_path)
        reference_scores = _scores(reference, drumscribe)
        competitor_scores = _scores(reference, competitor)
        app_f1 = float(reference_scores["50ms"]["micro"]["f1"])
        competitor_f1 = float(competitor_scores["50ms"]["micro"]["f1"])
        winner = (
            "drumscribe"
            if app_f1 > competitor_f1
            else "drum2notes"
            if competitor_f1 > app_f1
            else "tie"
        )
        wins[winner] += 1
        references.append(reference)
        drumscribe_predictions.append(drumscribe)
        competitor_predictions.append(competitor)
        rows.append(
            {
                "sequence": sequence,
                "recordId": record["recordId"],
                "dataset": record["dataset"],
                "title": record["title"],
                "genre": record["genre"],
                "performanceType": record["performanceType"],
                "drum2notesState": state,
                "drum2notesJobId": job.get("id"),
                "drum2notesEstimatedBpm": competitor_bpm,
                "winnerAt50ms": winner,
                "eventCounts": {
                    "reference": len(reference),
                    "drumscribe": len(drumscribe),
                    "drum2notes": len(competitor),
                },
                "scores": {
                    "drumscribe": reference_scores,
                    "drum2notes": competitor_scores,
                },
                "hashes": {
                    "fullMixExcerpt": record["audioSha256"],
                    "reference": record["referenceSha256"],
                    "drumStem": record["stemSha256"],
                    "drumscribePrediction": sha256(prediction_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.exists()
                    else None,
                },
            }
        )

    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "100 real-song excerpt production-v3 live comparison",
            "status": "opened_development_same_audio_live_comparison",
            "recordCount": len(records),
            "uniqueAudioHashCount": len({record["audioSha256"] for record in records}),
            "windowSecondsPerRecord": WINDOW_SECONDS,
            "totalScoredAudioSeconds": len(records) * WINDOW_SECONDS,
            "inputType": "full musical mixtures, not isolated drum tracks",
            "composition": {"RWC Popular": 89, "MDB Drums": 11},
            "genreCount": len({record["genre"] for record in records}),
            "genreCoverage": sorted({record["genre"] for record in records}),
            "primaryMetric": "five-family class-aware micro F1 at 50ms",
            "families": sorted(FAMILY5),
            "matcher": "five-family class-aware one-to-one onset matching",
            "referenceUnisonRule": "exact same-time events in one family count once",
            "tolerancesMilliseconds": list(TOLERANCES_MS),
            "predictionsGeneratedFreshForBenchmark": True,
            "sameAudioBytesForBothSystems": True,
            "separation": "hash-validated cached htdemucs_ft stems from the same excerpts",
            "researchOnly": True,
            "competitorFailurePolicy": "Any item without a usable result is retained as zero predictions.",
            "limitations": [
                "This is an opened development benchmark, not a sealed or independent audit.",
                "The suite covers 13 declared styles, not every musical genre in existence.",
                "RWC Popular contains commercial-style full mixtures with live, sequenced, and looped drums; MDB supplies 11 live full-band performances.",
                "Only 20-second excerpts are scored because the competitor public demo transcribes 20 seconds.",
                "RWC Popular and MDB Drums licenses restrict this evidence to non-commercial research use.",
                "Several MDB genres contain one song, so their per-genre scores have high uncertainty.",
                "A benchmark result does not prove universal accuracy on arbitrary user songs.",
            ],
        },
        "systems": {
            "drumscribe": {
                "provider": MODEL_VERSION,
                "pipeline": "htdemucs_ft + guarded direct/stem ADTOF fusion + first-party articulation recovery",
                "commercialRightsReference": APPROVAL_REFERENCE,
                "productionProviderGatePassed": True,
            },
            "drum2notes": {
                "product": "Klangio Drum2Notes",
                "surface": "live public demo",
                "modelSetting": "solo / all drum notes",
                "resultStates": dict(sorted(states.items())),
            },
        },
        "aggregate": {
            "drumscribe": _aggregate(references, drumscribe_predictions),
            "drum2notes": _aggregate(references, competitor_predictions),
        },
        "trackWinsAt50ms": dict(sorted(wins.items())),
        "datasets": _group_scores(
            records,
            references,
            drumscribe_predictions,
            competitor_predictions,
            "dataset",
        ),
        "genres": _group_scores(
            records,
            references,
            drumscribe_predictions,
            competitor_predictions,
            "genre",
        ),
        "performanceTypes": _group_scores(
            records,
            references,
            drumscribe_predictions,
            competitor_predictions,
            "performanceType",
        ),
        "tracks": rows,
        "processingSeconds": round(processing_seconds, 3)
        if processing_seconds is not None
        else None,
    }


def write_selection_manifest(records: list[dict[str, Any]], destination: Path) -> None:
    payload = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "status": "selection_and_references_frozen_before_inference",
        "selectionRule": "all 89 available RWC Popular clips followed by the fixed MDB test11 partition",
        "recordCount": len(records),
        "records": [
            {
                "sequence": record["sequence"],
                "recordId": record["recordId"],
                "dataset": record["dataset"],
                "title": record["title"],
                "genre": record["genre"],
                "performanceType": record["performanceType"],
                "audioSha256": record["audioSha256"],
                "stemSha256": record["stemSha256"],
                "referenceSha256": record["referenceSha256"],
                "referenceEventCount": len(record["reference"]),
            }
            for record in records
        ],
    }
    write_json(destination, payload)


def validate_selection_manifest(
    records: list[dict[str, Any]], selection_path: Path
) -> None:
    retained = json.loads(selection_path.read_text(encoding="utf-8"))
    expected = [
        (record["sequence"], record["recordId"], record["audioSha256"])
        for record in records
    ]
    actual = [
        (record.get("sequence"), record.get("recordId"), record.get("audioSha256"))
        for record in retained.get("records", [])
    ]
    if retained.get("recordCount") != 100 or actual != expected:
        raise RuntimeError(f"retained selection manifest changed: {selection_path}")


def write_compact_report(
    report: dict[str, Any],
    full_report_path: Path,
    selection_path: Path,
    destination: Path,
) -> None:
    compact_tracks = [
        {
            "sequence": row["sequence"],
            "recordId": row["recordId"],
            "dataset": row["dataset"],
            "genre": row["genre"],
            "performanceType": row["performanceType"],
            "drum2notesState": row["drum2notesState"],
            "winnerAt50ms": row["winnerAt50ms"],
            "eventCounts": row["eventCounts"],
            "f1At50ms": {
                system: row["scores"][system]["50ms"]["micro"]["f1"]
                for system in ("drumscribe", "drum2notes")
            },
            "fullMixSha256": row["hashes"]["fullMixExcerpt"],
        }
        for row in report["tracks"]
    ]
    write_json(
        destination,
        {
            "schemaVersion": 1,
            "createdAt": report["createdAt"],
            "benchmark": report["benchmark"],
            "systems": report["systems"],
            "aggregate": report["aggregate"],
            "trackWinsAt50ms": report["trackWinsAt50ms"],
            "datasets": report["datasets"],
            "genres": report["genres"],
            "performanceTypes": report["performanceTypes"],
            "tracks": compact_tracks,
            "evidence": {
                "fullReportRelativePath": str(
                    full_report_path.relative_to(REPOSITORY_ROOT)
                ),
                "fullReportSha256": sha256(full_report_path),
                "selectionManifestRelativePath": str(
                    selection_path.relative_to(REPOSITORY_ROOT)
                ),
                "selectionManifestSha256": sha256(selection_path),
                "rawDrumScribePredictionCount": 100,
                "rawDrum2NotesJobCount": 100,
                "rawDrum2NotesMusicJsonCount": 100,
            },
        },
    )


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if args.poll_seconds <= 0 or args.timeout_seconds <= 0:
        raise ValueError("poll and timeout values must be positive")
    repository = args.repository.resolve(strict=True)
    rwc_roots = args.rwc_root or list(DEFAULT_RWC_ROOTS)
    mdb_dataset = resolve(repository, args.mdb_dataset)
    mdb_source = resolve(repository, args.mdb_source)
    mdb_stem_evidence = resolve(repository, args.mdb_stem_evidence)
    output_root = resolve(repository, args.output, strict=False)
    compact_output = resolve(repository, args.compact_output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    records = load_records(
        repository,
        rwc_roots,
        mdb_dataset,
        mdb_source,
        mdb_stem_evidence,
    )
    selection_path = output_root / "selection-manifest.json"
    if not selection_path.exists():
        write_selection_manifest(records, selection_path)
    else:
        validate_selection_manifest(records, selection_path)

    started = time.monotonic()
    if not args.score_only:
        run_predictions(records, repository, output_root, args)
    retained_processing_seconds = None
    retained_report_path = output_root / "benchmark-result.json"
    if args.score_only and retained_report_path.exists():
        retained_processing_seconds = json.loads(
            retained_report_path.read_text(encoding="utf-8")
        ).get("processingSeconds")
    report = build_report(
        records,
        output_root,
        retained_processing_seconds if args.score_only else time.monotonic() - started,
    )
    destination = output_root / "benchmark-result.json"
    write_json(destination, report)
    write_compact_report(report, destination, selection_path, compact_output)
    print(
        json.dumps(
            {
                "output": str(destination),
                "states": report["systems"]["drum2notes"]["resultStates"],
                "wins": report["trackWinsAt50ms"],
                "f1At50ms": {
                    system: round(result["50ms"]["micro"]["f1"] * 100, 2)
                    for system, result in report["aggregate"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
