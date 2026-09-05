#!/usr/bin/env python3
"""Run a fresh same-audio DrumScribe versus Drum2Notes genre benchmark.

The suite has two explicitly separated strata:

* twenty previously unbenchmarked Google Magenta Groove recordings, selected
  without reading the annotations and balanced over four broad style groups;
* all four mixes in the official STAR Drums preview, which exercise the full
  Demucs -> ADTOF application path on music mixtures.

The Groove recordings are real human electronic-drum performances rather than
complete songs. STAR mixes contain real melodic/vocal recordings and aligned
re-synthesized drums. The report preserves this distinction.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPTS_ROOT.parent
for source_root in (
    SCRIPTS_ROOT,
    SCRIPTS_ROOT / "model_runners",
    REPOSITORY_ROOT / "packages" / "music-engine" / "src",
    REPOSITORY_ROOT / "ml" / "src",
):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

from drumscribe_music.licensing import require_production_safe
from drumscribe_music.providers.demucs import DemucsAdapter
from drumscribe_music.providers.external import (
    ADTOFResearchTranscriptionProvider,
    DrumScribeRecallFusionTranscriptionProvider,
)
from run_100_track_genre_benchmark import (
    CATEGORY_ORDER,
    category_for_style,
    style_from_audio,
)
from run_competitive_drum_benchmark import (
    FAMILY_SIX_MAP,
    competitor_events,
    reference_events,
    sha256,
)
from run_drum2notes_100_track_benchmark import (
    API_ROOT,
    poll,
    request_bytes,
    write_json,
)
from run_mdb_real_benchmark import _combine_event_lists, score
from run_owner_approved_adtof_mdb import resolve, resolve_executable

APPROVAL_REFERENCE = "OWNER-ATTESTATION-2026-09-05"
SELECTION_SEED = "drumscribe-novel-cross-genre-live-v1"
WINDOW_SECONDS = 20.0
RECORDS_PER_CATEGORY = 5
TOLERANCES_MS = (20, 50, 100)
DEFAULT_PREPARED = Path("data/licensed-corpus/groove-prepared/prepared-dataset.json")
DEFAULT_PRIOR_RESULTS = (
    Path("output/competitive-benchmark-2026-09-02/benchmark-result.json"),
    Path("output/100-track-genre-benchmark-2026-09-03/benchmark-result.json"),
)
DEFAULT_STAR_ROOT = Path(
    "data/research-corpus/star-drums-preview/star_drums_preview"
)
DEFAULT_OUTPUT = Path("output/novel-cross-genre-live-v1-2026-09-05")
DEFAULT_DEMUCS_PYTHON = Path("apps/api/.venv/bin/python")
DEFAULT_ADTOF_PYTHON = Path(".research-models/adtof-env/bin/python")
DEFAULT_ADTOF_RUNNER = Path("scripts/model_runners/adtof_runner.py")
DEFAULT_ADTOF_EXECUTABLE = Path(".research-models/adtof-env/bin/adtof")

FIVE_FAMILY_MAP = {
    instrument: family
    for instrument, family in FAMILY_SIX_MAP.items()
    if family != "TAMBOURINE"
}
STAR_FIVE_CLASS_MAP = {
    "BD": "KICK",
    "SD": "SNARE",
    "CHH": "HIHAT",
    "PHH": "HIHAT",
    "OHH": "HIHAT",
    "HT": "TOM",
    "MT": "TOM",
    "LT": "TOM",
    "CRC": "CYMBAL",
    "SPC": "CYMBAL",
    "CHC": "CYMBAL",
    "RD": "CYMBAL",
}
Event = tuple[float, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--star-root", type=Path, default=DEFAULT_STAR_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--demucs-python", type=Path, default=DEFAULT_DEMUCS_PYTHON)
    parser.add_argument("--adtof-python", type=Path, default=DEFAULT_ADTOF_PYTHON)
    parser.add_argument("--adtof-runner", type=Path, default=DEFAULT_ADTOF_RUNNER)
    parser.add_argument(
        "--adtof-executable", type=Path, default=DEFAULT_ADTOF_EXECUTABLE
    )
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--poll-seconds", type=float, default=4.0)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--score-only", action="store_true")
    return parser.parse_args()


def selection_rank(track_id: str) -> str:
    return hashlib.sha256(f"{SELECTION_SEED}:{track_id}".encode()).hexdigest()


def benchmark_category(style: str) -> str:
    try:
        return category_for_style(style)
    except RuntimeError:
        if style.startswith(("dance-breakbeat",)):
            return "funk_hiphop"
        if style.startswith(("dance-disco", "blues")):
            return "pop_soul"
        if style.startswith(("afrobeat", "middleeastern")):
            return "jazz_world"
        raise


def prior_audio_hashes(repository: Path) -> set[str]:
    result: set[str] = set()
    for relative in DEFAULT_PRIOR_RESULTS:
        path = resolve(repository, relative)
        payload = json.loads(path.read_text(encoding="utf-8"))
        result.update(str(track["audioSha256"]) for track in payload["tracks"])
    return result


def choose_groove_records(
    prepared_path: Path, excluded_hashes: set[str]
) -> list[dict[str, Any]]:
    payload = json.loads(prepared_path.read_text(encoding="utf-8"))
    candidates: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for record in payload["records"]:
        if record.get("split") != "train":
            continue
        if float(record["durationSeconds"]) < WINDOW_SECONDS:
            continue
        if str(record["audioSha256"]) in excluded_hashes:
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


def star_items(star_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for annotation in sorted(star_root.glob("data/**/annotation/*.txt")):
        audio = annotation.parent.parent / "audio" / "mix" / (
            annotation.stem + ".flac"
        )
        if not audio.is_file():
            raise FileNotFoundError(audio)
        relative = annotation.relative_to(star_root)
        split = relative.parts[1]
        source_collection = relative.parts[2] if split == "training" else "medleydb"
        style = "rock" if "Rock" in annotation.stem else source_collection
        rows.append(
            {
                "trackId": f"star/{annotation.stem}",
                "audioPath": str(audio.resolve()),
                "annotationPath": str(annotation.resolve()),
                "audioSha256": sha256(audio),
                "durationSeconds": audio_duration(audio),
                "split": split,
                "style": style,
                "category": "star_full_mix",
                "sourceCollection": source_collection,
            }
        )
    if len(rows) != 4:
        raise RuntimeError(f"expected four STAR preview mixes; found {len(rows)}")
    return rows


def audio_duration(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        os.fspath(path),
    ]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=60
    )
    return float(completed.stdout.strip())


def make_clip(source: Path, destination: Path, seconds: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        os.fspath(source),
        "-t",
        f"{seconds:.6f}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        os.fspath(destination),
    ]
    subprocess.run(command, check=True, timeout=180)


def count_reference_events(item: dict[str, Any]) -> int:
    return len(item_reference_events(item))


def item_reference_events(item: dict[str, Any]) -> list[Event]:
    limit = float(item["scoredSeconds"])
    annotation = Path(item["annotationPath"])
    if item["dataset"] == "groove":
        detailed = reference_events(annotation, limit)
        return sorted(
            (onset, FIVE_FAMILY_MAP[instrument])
            for onset, instrument in detailed
            if instrument in FIVE_FAMILY_MAP
        )
    events: list[Event] = []
    for line in annotation.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        onset = float(parts[0])
        family = STAR_FIVE_CLASS_MAP.get(parts[1])
        if family and 0 <= onset < limit:
            events.append((onset, family))
    return sorted(events)


def prepare_manifest(
    repository: Path,
    prepared_path: Path,
    star_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    manifest_path = output_root / "selection-manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    if (output_root / "drumscribe-raw").exists() or (
        output_root / "drum2notes-raw"
    ).exists():
        raise RuntimeError("prediction output exists before selection was frozen")

    selected = choose_groove_records(prepared_path, prior_audio_hashes(repository))
    selected.extend(star_items(star_root))
    items: list[dict[str, Any]] = []
    for sequence, record in enumerate(selected, 1):
        source = Path(record["audioPath"]).resolve(strict=True)
        scored_seconds = min(WINDOW_SECONDS, float(record["durationSeconds"]))
        clip = output_root / "inputs" / f"{sequence:03d}.wav"
        make_clip(source, clip, scored_seconds)
        item = {
            "sequence": sequence,
            "trackId": str(record["trackId"]),
            "dataset": "star_drums_preview"
            if str(record["trackId"]).startswith("star/")
            else "groove",
            "inputKind": "full_music_mix"
            if str(record["trackId"]).startswith("star/")
            else "real_human_drum_performance",
            "style": str(record["style"]),
            "category": str(record["category"]),
            "sourceSplit": str(record["split"]),
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
        "benchmarkId": SELECTION_SEED,
        "selectionFrozenBeforeInference": True,
        "selectionUsesReferenceLabels": False,
        "windowSecondsMaximum": WINDOW_SECONDS,
        "items": items,
    }
    write_json(manifest_path, manifest)
    return manifest


def verify_manifest_items(items: list[dict[str, Any]]) -> None:
    for item in items:
        audio = Path(item["audioPath"]).resolve(strict=True)
        annotation = Path(item["annotationPath"]).resolve(strict=True)
        if sha256(audio) != item["audioSha256"]:
            raise RuntimeError(f"benchmark audio changed: {audio}")
        if sha256(annotation) != item["annotationSha256"]:
            raise RuntimeError(f"benchmark annotation changed: {annotation}")


def submit(audio_path: Path, title: str, composer: str) -> str:
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
            "title": title,
            "composer": composer,
            "agreedToTerms": True,
        },
    }
    command = [
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
        f"title={title}",
    ]
    completed = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=150
    )
    payload = json.loads(completed.stdout)
    job_id = str(payload.get("jobId", ""))
    if not job_id:
        raise RuntimeError(f"upload returned no jobId: {payload}")
    return job_id


def process_competitor(
    item: dict[str, Any],
    raw_root: Path,
    poll_seconds: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    sequence = int(item["sequence"])
    stem = f"{sequence:03d}"
    job_path = raw_root / f"{stem}.job.json"
    music_path = raw_root / f"{stem}.music.json"
    if job_path.exists():
        retained = json.loads(job_path.read_text(encoding="utf-8"))
        if retained.get("state") == "ok" and music_path.exists():
            return retained
        job_id = str(retained.get("id") or retained.get("jobId") or "")
    else:
        job_id = ""
    try:
        if not job_id:
            job_id = submit(
                Path(item["audioPath"]),
                f"Novel genre benchmark {sequence:03d}",
                "STAR Drums" if item["dataset"] == "star_drums_preview" else "GMD",
            )
            write_json(
                job_path,
                {
                    "id": job_id,
                    "state": "submitted",
                    "sequence": sequence,
                    "sourceAudioSha256": item["audioSha256"],
                },
            )
        payload = poll(job_id, poll_seconds, timeout_seconds)
        retained = {
            **payload,
            "sequence": sequence,
            "sourceAudioSha256": item["audioSha256"],
        }
        write_json(job_path, retained)
        if payload.get("state") == "ok":
            query = urllib.parse.urlencode({"id": job_id})
            music_path.write_bytes(request_bytes(f"{API_ROOT}/musj?{query}"))
        return retained
    except (
        OSError,
        RuntimeError,
        TimeoutError,
        ValueError,
        subprocess.SubprocessError,
        urllib.error.URLError,
    ) as error:
        retained = {
            "id": job_id or None,
            "state": "runner_error",
            "sequence": sequence,
            "sourceAudioSha256": item["audioSha256"],
            "runnerError": f"{type(error).__name__}: {error}",
        }
        write_json(job_path, retained)
        return retained


def mapped_prediction_events(payload: dict[str, Any], limit: float) -> list[Event]:
    return sorted(
        (float(hit["onsetSeconds"]), FIVE_FAMILY_MAP[str(hit["instrument"])])
        for hit in payload["hits"]
        if str(hit["instrument"]) in FIVE_FAMILY_MAP
        and 0 <= float(hit["onsetSeconds"]) < limit
    )


def aggregate(references: list[list[Event]], predictions: list[list[Event]]) -> dict[str, Any]:
    combined_reference = _combine_event_lists(references)
    combined_prediction = _combine_event_lists(predictions)
    return {
        f"{milliseconds}ms": score(
            combined_reference, combined_prediction, milliseconds / 1_000
        )
        for milliseconds in TOLERANCES_MS
    }


def score_results(items: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    drumscribe_root = output_root / "drumscribe-raw"
    competitor_root = output_root / "drum2notes-raw"
    all_reference: list[list[Event]] = []
    all_drumscribe: list[list[Event]] = []
    all_competitor: list[list[Event]] = []
    grouped_reference: dict[str, list[list[Event]]] = defaultdict(list)
    grouped_drumscribe: dict[str, list[list[Event]]] = defaultdict(list)
    grouped_competitor: dict[str, list[list[Event]]] = defaultdict(list)
    states: Counter[str] = Counter()
    tracks: list[dict[str, Any]] = []

    for item in items:
        sequence = int(item["sequence"])
        stem = f"{sequence:03d}"
        reference = item_reference_events(item)
        prediction_path = drumscribe_root / f"{stem}.json"
        prediction_payload = json.loads(prediction_path.read_text(encoding="utf-8"))
        drumscribe = mapped_prediction_events(
            prediction_payload, float(item["scoredSeconds"])
        )
        job_path = competitor_root / f"{stem}.job.json"
        music_path = competitor_root / f"{stem}.music.json"
        job = (
            json.loads(job_path.read_text(encoding="utf-8"))
            if job_path.exists()
            else {"state": "missing"}
        )
        state = str(job.get("state", "missing"))
        states[state] += 1
        competitor: list[Event] = []
        competitor_bpm: float | None = None
        if state == "ok" and music_path.exists():
            detailed, competitor_bpm = competitor_events(
                music_path, float(item["scoredSeconds"])
            )
            competitor = sorted(
                (onset, FIVE_FAMILY_MAP[instrument])
                for onset, instrument in detailed
                if instrument in FIVE_FAMILY_MAP
            )

        group = str(item["category"])
        all_reference.append(reference)
        all_drumscribe.append(drumscribe)
        all_competitor.append(competitor)
        grouped_reference[group].append(reference)
        grouped_drumscribe[group].append(drumscribe)
        grouped_competitor[group].append(competitor)
        tracks.append(
            {
                "sequence": sequence,
                "trackId": item["trackId"],
                "dataset": item["dataset"],
                "inputKind": item["inputKind"],
                "style": item["style"],
                "category": group,
                "audioSha256": item["audioSha256"],
                "scoredSeconds": item["scoredSeconds"],
                "drum2notesState": state,
                "drum2notesJobId": job.get("id"),
                "drum2notesEstimatedBpm": competitor_bpm,
                "eventCounts": {
                    "reference": len(reference),
                    "drumscribe": len(drumscribe),
                    "drum2notes": len(competitor),
                },
                "scores": {
                    f"{milliseconds}ms": {
                        "drumscribe": score(
                            reference, drumscribe, milliseconds / 1_000
                        ),
                        "drum2notes": score(
                            reference, competitor, milliseconds / 1_000
                        ),
                    }
                    for milliseconds in TOLERANCES_MS
                },
                "hashes": {
                    "referenceAnnotation": item["annotationSha256"],
                    "drumscribePrediction": sha256(prediction_path),
                    "drum2notesRaw": sha256(music_path)
                    if music_path.exists()
                    else None,
                },
            }
        )

    categories = {
        group: {
            "recordCount": len(grouped_reference[group]),
            "drumscribe": aggregate(
                grouped_reference[group], grouped_drumscribe[group]
            ),
            "drum2notes": aggregate(
                grouped_reference[group], grouped_competitor[group]
            ),
        }
        for group in (*CATEGORY_ORDER, "star_full_mix")
    }
    manifest_path = output_root / "selection-manifest.json"
    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "Novel cross-genre real-performance and STAR full-mix comparison",
            "status": "development_comparison_not_independent_sealed_audit",
            "trackCount": len(items),
            "grooveTrackCount": sum(item["dataset"] == "groove" for item in items),
            "starFullMixTrackCount": sum(
                item["dataset"] == "star_drums_preview" for item in items
            ),
            "totalScoredAudioSeconds": sum(
                float(item["scoredSeconds"]) for item in items
            ),
            "primaryMetric": "five-family class-aware micro F1 at 50ms",
            "families": ["KICK", "SNARE", "HIHAT", "TOM", "CYMBAL"],
            "datasetLicenses": {
                "groove": "CC BY 4.0",
                "starDrumsPreview": "source-specific Creative Commons terms; research evaluation only",
            },
            "researchOnly": True,
            "sameAudioBytesForBothSystems": True,
            "selectionFrozenBeforeInference": True,
            "selectionManifestSha256": sha256(manifest_path),
            "selectionUsedReferenceLabels": False,
            "competitorFailurePolicy": (
                "Accepted items without usable output remain in the primary score as zero predictions."
            ),
            "limitations": [
                "The twenty Groove items are isolated electronic-drum performances by real drummers, not complete songs.",
                "STAR mixes contain real melodic/vocal recordings with reference-aligned re-synthesized drums.",
                "The selected ADTOF weights were not trained or tuned on GMD during this run, but other retired first-party research models used the GMD train split and this repository is not an independent audit environment.",
                "Four broad Groove style groups and the four-item STAR preview are representative strata, not every musical genre.",
                "Drum2Notes is measured through its live public demo and audio-aligned MusicJSON result.",
            ],
        },
        "systems": {
            "drumscribe": {
                "drumOnlyPipeline": "ADTOF-pytorch -> rhythm-consistency-v1",
                "fullMixPipeline": "htdemucs_ft -> ADTOF-pytorch -> rhythm-consistency-v1",
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
            "drumscribe": aggregate(all_reference, all_drumscribe),
            "drum2notes": aggregate(all_reference, all_competitor),
        },
        "categories": categories,
        "tracks": tracks,
    }


def run_inference(
    repository: Path,
    items: list[dict[str, Any]],
    output_root: Path,
    args: argparse.Namespace,
) -> None:
    raw_root = output_root / "drum2notes-raw"
    prediction_root = output_root / "drumscribe-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    prediction_root.mkdir(parents=True, exist_ok=True)
    if any(prediction_root.iterdir()):
        raise RuntimeError(f"fresh DrumScribe output is not empty: {prediction_root}")

    adtof_python = resolve_executable(repository, args.adtof_python)
    recall_fusion_runner = getattr(args, "recall_fusion_runner", None)
    if recall_fusion_runner is not None:
        recall_fusion_command = [
            str(adtof_python),
            str(resolve(repository, recall_fusion_runner)),
            "--repository",
            str(repository),
            "--device",
            args.device,
        ]
        drum_only_profile = getattr(args, "drum_only_profile", None)
        if drum_only_profile is not None:
            recall_fusion_command.extend(
                ("--drum-only-profile", str(drum_only_profile))
            )
        transcription = DrumScribeRecallFusionTranscriptionProvider(
            tuple(recall_fusion_command),
            model_version="drumscribe-recall-fusion-v2",
            timeout_seconds=3_600,
        )
        decoder = "drumscribe-recall-fusion-v2"
    else:
        adtof_runner = resolve(repository, args.adtof_runner)
        adtof_executable = resolve_executable(repository, args.adtof_executable)
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
        decoder = "rhythm-consistency-v1"
    separation = DemucsAdapter(
        model="htdemucs_ft",
        python_executable=str(resolve_executable(repository, args.demucs_python)),
    )
    require_production_safe(transcription, production=True)
    require_production_safe(separation, production=True)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_competitor,
                item,
                raw_root,
                args.poll_seconds,
                args.timeout_seconds,
            ): int(item["sequence"])
            for item in items
        }

        for completed, item in enumerate(items, 1):
            audio = Path(item["audioPath"])
            stem_hash: str | None = None
            if item["inputKind"] == "full_music_mix":
                with tempfile.TemporaryDirectory(
                    prefix="drumscribe-novel-benchmark-"
                ) as directory:
                    stem = Path(directory) / "drums.wav"
                    separation.separate_drums(audio, stem)
                    stem_hash = sha256(stem)
                    if hasattr(transcription, "transcribe_multiview"):
                        hits = transcription.transcribe_multiview(audio, stem)
                    else:
                        hits = transcription.transcribe(stem)
            else:
                hits = transcription.transcribe(audio)
            payload = {
                "schemaVersion": 1,
                "provider": transcription.provider_id,
                "modelVersion": transcription.version,
                "decoder": decoder,
                "commercialRightsReference": APPROVAL_REFERENCE,
                "source": {
                    "audioSha256": item["audioSha256"],
                    "inputKind": item["inputKind"],
                    "drumStemSha256": stem_hash,
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
            write_json(prediction_root / f"{int(item['sequence']):03d}.json", payload)
            print(
                json.dumps(
                    {
                        "system": "drumscribe",
                        "completed": completed,
                        "total": len(items),
                        "sequence": item["sequence"],
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
                        "total": len(items),
                        "sequence": futures[future],
                        "state": result.get("state"),
                    }
                ),
                flush=True,
            )


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if args.prepare_only and args.score_only:
        raise ValueError("--prepare-only and --score-only are mutually exclusive")
    repository = args.repository.resolve(strict=True)
    prepared_path = resolve(repository, args.prepared)
    star_root = resolve(repository, args.star_root)
    output_root = resolve(repository, args.output, strict=False)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = prepare_manifest(
        repository, prepared_path, star_root, output_root
    )
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
    report = score_results(items, output_root)
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
