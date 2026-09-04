#!/usr/bin/env python3
"""Prepare and score a frozen 50-song RWC Popular transcription benchmark.

This benchmark uses 20-second, drum-active excerpts from the CC BY-NC 4.0
RWC 2.0 Popular Music Database.  Its aligned General MIDI files provide the
reference drum events.  The command deliberately separates preparation from
inference so the selection and references are frozen before the model runs.

The benchmark is for local, non-commercial research.  It must not be used as
training data or redistributed with DrumScribe.
"""

from __future__ import annotations

import argparse
import binascii
import bz2
import csv
import hashlib
import io
import json
import lzma
import os
import re
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_ml.ensemble import StackedEnsembleConfig
from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel

SCRIPTS_ROOT = Path(__file__).resolve().parent
MODEL_RUNNERS_ROOT = SCRIPTS_ROOT / "model_runners"
for import_root in (SCRIPTS_ROOT, MODEL_RUNNERS_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from _midi_contract import midi_hits
from run_competitive_drum_benchmark import (
    CHECKPOINTS,
    TOLERANCES,
    combine_event_lists,
    load_models,
    predict_drumscribe,
    score_taxonomies,
    sha256,
)

ARCHIVE_URL = "https://zenodo.org/records/18656623/files/RWC-P.zip?download=1"
ARCHIVE_MD5 = "960a11a2d7fb603ad0dae8428f53d4f0"
ANNOTATIONS_URL = "https://github.com/rwc-music/rwc-annotations"
DATASET_PAGE = "https://zenodo.org/records/18656623"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
SELECTION_SEED = "drumscribe-rwc-popular-50-v1"
DEFAULT_ANNOTATIONS = Path("data/research-corpus/rwc-annotations")
DEFAULT_DATA_ROOT = Path("data/research-corpus/rwc-popular-50-v1")
DEFAULT_OUTPUT = Path("output/rwc-popular-50-v18/benchmark-result.json")
DEFAULT_CONFIG = Path("ml/configs/groove-stacked-articulation-v18.json")
DEFAULT_TRACK_COUNT = 50
DEFAULT_WINDOW_SECONDS = 20.0
DEFAULT_DEMUCS_MODEL = "htdemucs_ft"
MAX_ZIP_EXTRA_BYTES = 65_535
Event = tuple[float, str]


def resolve(repository: Path, path: Path, *, strict: bool = True) -> Path:
    candidate = path if path.is_absolute() else repository / path
    return candidate.resolve(strict=strict)


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_metadata(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def selection_score(rwc_id: str, seed: str = SELECTION_SEED) -> str:
    return hashlib.sha256(f"{seed}:{rwc_id}".encode()).hexdigest()


def select_popular_tracks(
    rows: list[dict[str, str]],
    count: int = DEFAULT_TRACK_COUNT,
    seed: str = SELECTION_SEED,
    offset: int = 0,
) -> list[dict[str, str]]:
    eligible = [
        row
        for row in rows
        if row.get("CollID") == "P"
        and row.get("DrumInformation", "").strip().casefold() != "without drums"
    ]
    ranked = sorted(
        eligible,
        key=lambda row: (selection_score(row["RWCID"], seed), row["RWCID"]),
    )
    if offset < 0:
        raise ValueError("selection offset must not be negative")
    if len(ranked) < offset + count:
        raise RuntimeError(
            f"only {len(ranked)} drum-containing RWC-P tracks; "
            f"need {offset + count} for offset {offset} and count {count}"
        )
    # The hash determines membership. Stable RWC ID order makes reports readable.
    return sorted(ranked[offset : offset + count], key=lambda row: row["RWCID"])


def drum_type(value: str) -> str:
    normalized = value.strip().casefold()
    if "live" in normalized:
        return "live"
    if "loop" in normalized:
        return "loops"
    if "sequence" in normalized:
        return "sequences"
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "unknown"


def active_window(
    events: list[Event], audio_start: float, audio_end: float, duration: float
) -> float:
    if duration <= 0 or audio_end <= audio_start:
        raise ValueError("invalid benchmark window or audio bounds")
    if audio_end - audio_start < duration:
        raise ValueError("audio is shorter than the requested benchmark window")
    if not events:
        raise ValueError("track has no supported General MIDI drum events")
    proposed = max(audio_start, events[0][0] - 1.0)
    return round(min(proposed, audio_end - duration), 6)


def window_events(events: list[Event], start: float, duration: float) -> list[Event]:
    end = start + duration
    return [
        (round(onset - start, 6), instrument)
        for onset, instrument in events
        if start <= onset < end
    ]


def annotation_commit(annotations_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", os.fspath(annotations_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_selection_manifest(
    annotations_root: Path,
    *,
    count: int,
    window_seconds: float,
    selection_offset: int = 0,
) -> dict[str, Any]:
    metadata_path = annotations_root / "metadata.csv"
    midi_root = (
        annotations_root / "01_annotations_preprocessed" / "MIDI_aligned" / "RWC-P"
    )
    rows = select_popular_tracks(
        load_metadata(metadata_path), count, offset=selection_offset
    )
    tracks: list[dict[str, Any]] = []
    for sequence, row in enumerate(rows, 1):
        rwc_id = row["RWCID"]
        midi_path = (midi_root / f"{rwc_id}.mid").resolve(strict=True)
        events = [
            (float(hit["onsetSeconds"]), str(hit["instrument"]))
            for hit in midi_hits(midi_path)
        ]
        start = active_window(
            events,
            float(row["audio_start"]),
            float(row["audio_end"]),
            window_seconds,
        )
        reference = window_events(events, start, window_seconds)
        if not reference:
            raise RuntimeError(f"selected window for {rwc_id} has no reference events")
        tracks.append(
            {
                "sequence": sequence,
                "rwcId": rwc_id,
                "title": row["Title"],
                "artist": row["Artist"],
                "language": row["SingingLanguage"] or "Instrumental/unspecified",
                "genreMain": row["GenreMain"],
                "genreSub": row["GenreSub"],
                "drumInformation": row["DrumInformation"],
                "drumType": drum_type(row["DrumInformation"]),
                "selectionScoreSha256": selection_score(rwc_id),
                "archiveEntry": f"RWC-P/{rwc_id}.wav",
                "clipRelativePath": f"clips/{rwc_id}.wav",
                "clipStartSeconds": start,
                "clipDurationSeconds": window_seconds,
                "clipSha256": None,
                "referenceMidiRelativePath": str(
                    midi_path.relative_to(annotations_root)
                ),
                "referenceMidiSha256": sha256(midi_path),
                "referenceEventCount": len(reference),
                "referenceEvents": [
                    {"onsetSeconds": onset, "instrument": instrument}
                    for onset, instrument in reference
                ],
            }
        )
    selection_claim = [
        {
            "rwcId": track["rwcId"],
            "selectionScoreSha256": track["selectionScoreSha256"],
            "clipStartSeconds": track["clipStartSeconds"],
            "clipDurationSeconds": track["clipDurationSeconds"],
            "referenceMidiSha256": track["referenceMidiSha256"],
            "referenceEvents": track["referenceEvents"],
        }
        for track in tracks
    ]
    return {
        "schemaVersion": 1,
        "benchmarkId": (
            "rwc-popular-50-v1"
            if selection_offset == 0 and count == DEFAULT_TRACK_COUNT
            else f"rwc-popular-offset-{selection_offset}-count-{count}-v1"
        ),
        "status": "selection_and_references_frozen_before_inference",
        "createdAt": datetime.now(UTC).isoformat(),
        "selectionSeed": SELECTION_SEED,
        "selectionOffset": selection_offset,
        "selectionRule": (
            "Exclude metadata rows marked 'Without drums'; rank the remaining RWC-P "
            "tracks by SHA-256(seed:RWCID); take the first N; report in RWCID order."
        ),
        "windowRule": (
            "Use 20 seconds beginning one second before the first supported GM drum "
            "event, bounded by the manually annotated music start and end."
        ),
        "selectionReferenceSha256": canonical_json_sha256(selection_claim),
        "recordCount": len(tracks),
        "totalScoredAudioSeconds": len(tracks) * window_seconds,
        "referenceEventCount": sum(track["referenceEventCount"] for track in tracks),
        "dataset": {
            "name": "RWC 2.0 Popular Music Database",
            "archiveUrl": ARCHIVE_URL,
            "archivePublishedMd5": ARCHIVE_MD5,
            "datasetPage": DATASET_PAGE,
            "annotationsUrl": ANNOTATIONS_URL,
            "annotationsCommit": annotation_commit(annotations_root),
            "license": "CC BY-NC 4.0",
            "licenseUrl": LICENSE_URL,
            "usage": "local non-commercial evaluation only",
        },
        "limitations": [
            "These are professionally produced popular-style songs, not a popularity-ranked chart list.",
            "The active-window location uses reference MIDI, but model predictions and thresholds do not.",
            "The aligned performance MIDI is the canonical event reference, not an engraved commercial score.",
            "Only 20 seconds per song are scored; results are not whole-song averages.",
            "The CC BY-NC 4.0 audio and annotations cannot be redistributed or used commercially here.",
        ],
        "tracks": tracks,
    }


class HttpRangeFetcher:
    def __init__(self, url: str, *, retries: int = 8) -> None:
        self.url = url
        self.retries = retries
        self.size = self._discover_size()

    def _request(self, start: int, end: int) -> bytes:
        if start < 0 or end < start:
            raise ValueError(f"invalid HTTP range {start}-{end}")
        request = urllib.request.Request(
            self.url,
            headers={
                "Range": f"bytes={start}-{end}",
                "User-Agent": "DrumScribe-RWC-benchmark/1.0",
            },
        )
        for attempt in range(self.retries):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    if response.status != 206:
                        raise RuntimeError(
                            f"server did not honor byte range: HTTP {response.status}"
                        )
                    return response.read()
            except urllib.error.HTTPError as error:
                if (
                    error.code not in {429, 500, 502, 503, 504}
                    or attempt + 1 == self.retries
                ):
                    raise
                retry_after = error.headers.get("Retry-After")
                delay = min(30.0, float(retry_after or 2**attempt))
                time.sleep(delay)
            except urllib.error.URLError:
                if attempt + 1 == self.retries:
                    raise
                time.sleep(min(30.0, 2**attempt))
        raise AssertionError("unreachable")

    def _discover_size(self) -> int:
        request = urllib.request.Request(
            self.url,
            headers={
                "Range": "bytes=0-0",
                "User-Agent": "DrumScribe-RWC-benchmark/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 206:
                raise RuntimeError(
                    "RWC archive server does not support HTTP byte ranges"
                )
            content_range = response.headers.get("Content-Range", "")
        match = re.fullmatch(r"bytes 0-0/(\d+)", content_range)
        if not match:
            raise RuntimeError(f"invalid Content-Range header: {content_range!r}")
        return int(match.group(1))

    def fetch(self, start: int, end: int) -> bytes:
        end = min(end, self.size - 1)
        payload = self._request(start, end)
        expected = end - start + 1
        if len(payload) != expected:
            raise RuntimeError(
                f"short HTTP range: received {len(payload)}; expected {expected}"
            )
        return payload


class RemoteRangeReader:
    def __init__(self, fetcher: HttpRangeFetcher) -> None:
        self.fetcher = fetcher
        self.position = 0

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.fetcher.size + offset
        else:
            raise ValueError(f"unsupported whence: {whence}")
        if position < 0:
            raise ValueError("negative seek position")
        self.position = position
        return position

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self.fetcher.size - self.position
        if size == 0 or self.position >= self.fetcher.size:
            return b""
        end = min(self.fetcher.size - 1, self.position + size - 1)
        payload = self.fetcher.fetch(self.position, end)
        self.position += len(payload)
        return payload

    def seekable(self) -> bool:
        return True


def decompress_zip_entry(fetcher: HttpRangeFetcher, info: zipfile.ZipInfo) -> bytes:
    if info.flag_bits & 0x1:
        raise RuntimeError(f"encrypted ZIP entry is unsupported: {info.filename}")
    # One request per song: the maximum legal ZIP extra field is included as padding.
    padded_size = 30 + len(info.filename.encode("utf-8")) + MAX_ZIP_EXTRA_BYTES
    blob = fetcher.fetch(
        info.header_offset,
        info.header_offset + padded_size + info.compress_size - 1,
    )
    if len(blob) < 30:
        raise RuntimeError(f"truncated local ZIP header for {info.filename}")
    header = struct.unpack("<IHHHHHIIIHH", blob[:30])
    if header[0] != 0x04034B50:
        raise RuntimeError(f"invalid local ZIP header for {info.filename}")
    method, name_length, extra_length = header[3], header[9], header[10]
    data_start = 30 + name_length + extra_length
    compressed = blob[data_start : data_start + info.compress_size]
    if len(compressed) != info.compress_size:
        raise RuntimeError(f"truncated compressed payload for {info.filename}")
    if method == zipfile.ZIP_STORED:
        output = compressed
    elif method == zipfile.ZIP_DEFLATED:
        output = zlib.decompress(compressed, -zlib.MAX_WBITS)
    elif method == zipfile.ZIP_BZIP2:
        output = bz2.decompress(compressed)
    elif method == zipfile.ZIP_LZMA:
        output = lzma.decompress(compressed)
    else:
        raise RuntimeError(f"unsupported ZIP compression method {method}")
    if len(output) != info.file_size:
        raise RuntimeError(f"uncompressed size mismatch for {info.filename}")
    if (binascii.crc32(output) & 0xFFFFFFFF) != info.CRC:
        raise RuntimeError(f"CRC mismatch for {info.filename}")
    return output


def write_audio_clip(
    archive_wav: bytes, destination: Path, *, start: float, duration: float
) -> None:
    import soundfile as sf

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.wav")
    with sf.SoundFile(io.BytesIO(archive_wav)) as source:
        start_frame = round(start * source.samplerate)
        frame_count = round(duration * source.samplerate)
        source.seek(start_frame)
        samples = source.read(frame_count, dtype="float32", always_2d=True)
        if len(samples) != frame_count:
            raise RuntimeError(
                f"short source clip for {destination.name}: {len(samples)} != {frame_count}"
            )
        sf.write(
            temporary,
            samples,
            source.samplerate,
            subtype="PCM_16",
            format="WAV",
        )
    temporary.replace(destination)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare(args: argparse.Namespace) -> int:
    repository = args.repository.resolve(strict=True)
    annotations_root = resolve(repository, args.annotations)
    data_root = resolve(repository, args.data_root, strict=False)
    manifest_path = data_root / "selection-manifest.json"
    manifest = build_selection_manifest(
        annotations_root,
        count=args.track_count,
        window_seconds=args.window_seconds,
        selection_offset=args.selection_offset,
    )
    # Persist the immutable selection and references before any model inference.
    write_json(manifest_path, manifest)
    fetcher = HttpRangeFetcher(args.archive_url)
    with zipfile.ZipFile(RemoteRangeReader(fetcher)) as archive:
        entries = {info.filename: info for info in archive.infolist()}

    def download(track: dict[str, Any]) -> tuple[str, str, str]:
        destination = data_root / track["clipRelativePath"]
        if destination.is_file():
            return track["rwcId"], sha256(destination), "existing"
        entry = track["archiveEntry"]
        if entry not in entries:
            raise RuntimeError(f"archive entry is missing: {entry}")
        archive_wav = decompress_zip_entry(fetcher, entries[entry])
        write_audio_clip(
            archive_wav,
            destination,
            start=float(track["clipStartSeconds"]),
            duration=float(track["clipDurationSeconds"]),
        )
        return track["rwcId"], sha256(destination), "downloaded"

    tracks_by_id = {track["rwcId"]: track for track in manifest["tracks"]}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(download, track) for track in manifest["tracks"]]
        for future in as_completed(futures):
            rwc_id, digest, status = future.result()
            tracks_by_id[rwc_id]["clipSha256"] = digest
            write_json(manifest_path, manifest)
            print(
                json.dumps({"clip": rwc_id, "status": status, "sha256": digest}),
                flush=True,
            )
    manifest["preparedAt"] = datetime.now(UTC).isoformat()
    manifest["archiveSizeBytes"] = fetcher.size
    write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "tracks": len(manifest["tracks"]),
                "referenceEvents": manifest["referenceEventCount"],
            },
            indent=2,
        )
    )
    return 0


def load_and_validate_manifest(data_root: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = (data_root / "selection-manifest.json").resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "selection_and_references_frozen_before_inference":
        raise RuntimeError("selection manifest is not frozen")
    for track in manifest["tracks"]:
        clip = (data_root / track["clipRelativePath"]).resolve(strict=True)
        expected = track.get("clipSha256")
        if not expected or sha256(clip) != expected:
            raise RuntimeError(f"clip checksum mismatch: {track['rwcId']}")
    return manifest_path, manifest


def separate(args: argparse.Namespace) -> int:
    repository = args.repository.resolve(strict=True)
    data_root = resolve(repository, args.data_root)
    manifest_path, manifest = load_and_validate_manifest(data_root)
    demucs_root = data_root / "demucs"
    missing = [
        track
        for track in manifest["tracks"]
        if not (
            demucs_root / args.demucs_model / track["rwcId"] / "drums.wav"
        ).is_file()
    ]
    if missing:
        command = [
            "uv",
            "run",
            "--project",
            os.fspath(repository / "packages/music-engine"),
            "--extra",
            "demucs",
            "python",
            "-m",
            "demucs.separate",
            "--two-stems",
            "drums",
            "--name",
            args.demucs_model,
            "--out",
            os.fspath(demucs_root),
            *[os.fspath(data_root / track["clipRelativePath"]) for track in missing],
        ]
        subprocess.run(command, cwd=repository, check=True)
    stems = []
    for track in manifest["tracks"]:
        stem = (demucs_root / args.demucs_model / track["rwcId"] / "drums.wav").resolve(
            strict=True
        )
        stems.append(
            {
                "rwcId": track["rwcId"],
                "sourceClipSha256": track["clipSha256"],
                "drumsRelativePath": str(stem.relative_to(data_root)),
                "drumsSha256": sha256(stem),
            }
        )
    separation_manifest = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "sourceSelectionManifestSha256": sha256(manifest_path),
        "provider": "Demucs",
        "model": args.demucs_model,
        "mode": "two-stems drums",
        "researchOnly": True,
        "stems": stems,
    }
    output = data_root / "separation-manifest.json"
    write_json(output, separation_manifest)
    print(json.dumps({"manifest": str(output), "stems": len(stems)}, indent=2))
    return 0


def choose_device(requested: str) -> str:
    import torch

    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def aggregate_scores(
    references: list[list[Event]], predictions: list[list[Event]]
) -> dict[str, Any]:
    combined_reference = combine_event_lists(references)
    combined_prediction = combine_event_lists(predictions)
    return {
        str(round(tolerance * 1_000)): score_taxonomies(
            combined_reference, combined_prediction, tolerance
        )
        for tolerance in TOLERANCES
    }


def reference_events_from_track(track: dict[str, Any]) -> list[Event]:
    return [
        (float(event["onsetSeconds"]), str(event["instrument"]))
        for event in track["referenceEvents"]
    ]


def evaluate(args: argparse.Namespace) -> int:
    repository = args.repository.resolve(strict=True)
    data_root = resolve(repository, args.data_root)
    config_path = resolve(repository, args.config)
    output_path = resolve(repository, args.output, strict=False)
    manifest_path, manifest = load_and_validate_manifest(data_root)
    separation_path = (data_root / "separation-manifest.json").resolve(strict=True)
    separation = json.loads(separation_path.read_text(encoding="utf-8"))
    if separation["sourceSelectionManifestSha256"] != sha256(manifest_path):
        raise RuntimeError(
            "separation manifest does not match frozen selection manifest"
        )
    stems = {stem["rwcId"]: stem for stem in separation["stems"]}
    feature_root = data_root / "features" / separation["model"]
    raw_root = output_path.parent / "drumscribe-raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    preparation = PreparationConfig(
        seed="rwc-popular-50-v18-inference", augmentation_variants=0
    )
    feature_paths: dict[str, Path] = {}
    for track in manifest["tracks"]:
        rwc_id = track["rwcId"]
        stem_info = stems[rwc_id]
        stem = (data_root / stem_info["drumsRelativePath"]).resolve(strict=True)
        if sha256(stem) != stem_info["drumsSha256"]:
            raise RuntimeError(f"separated stem checksum mismatch: {rwc_id}")
        feature = feature_root / f"{rwc_id}.npz"
        if not feature.exists():
            cache_log_mel(stem, feature, preparation)
        feature_paths[rwc_id] = feature
        print(json.dumps({"features": rwc_id}), flush=True)

    configuration = StackedEnsembleConfig.load(config_path)
    checkpoint_paths = {
        name: resolve(repository, CHECKPOINTS[name]) for name in configuration.models
    }
    device = choose_device(args.device)
    first_feature = feature_paths[manifest["tracks"][0]["rwcId"]]
    with np.load(first_feature, allow_pickle=False) as arrays:
        mel_bands = int(arrays["features"].shape[1])
    models = load_models(configuration, checkpoint_paths, mel_bands, device)

    all_reference: list[list[Event]] = []
    all_prediction: list[list[Event]] = []
    grouped_reference: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    grouped_prediction: dict[str, dict[str, list[list[Event]]]] = {
        "drumType": defaultdict(list),
        "language": defaultdict(list),
    }
    tracks: list[dict[str, Any]] = []
    for track in manifest["tracks"]:
        rwc_id = track["rwcId"]
        duration = float(track["clipDurationSeconds"])
        reference = reference_events_from_track(track)
        prediction = predict_drumscribe(
            feature_paths[rwc_id], models, configuration, device, duration
        )
        all_reference.append(reference)
        all_prediction.append(prediction)
        for group_name in grouped_reference:
            key = str(track[group_name])
            grouped_reference[group_name][key].append(reference)
            grouped_prediction[group_name][key].append(prediction)
        raw_path = raw_root / f"{rwc_id}.json"
        write_json(
            raw_path,
            {
                "schemaVersion": 1,
                "modelVersion": configuration.model_version,
                "sourceStemSha256": stems[rwc_id]["drumsSha256"],
                "events": [
                    {"onsetSeconds": onset, "instrument": instrument}
                    for onset, instrument in prediction
                ],
            },
        )
        track_result = {
            key: track[key]
            for key in (
                "sequence",
                "rwcId",
                "title",
                "artist",
                "language",
                "genreMain",
                "genreSub",
                "drumInformation",
                "drumType",
                "clipStartSeconds",
                "clipDurationSeconds",
                "clipSha256",
                "referenceMidiSha256",
            )
        }
        track_result.update(
            {
                "drumsStemSha256": stems[rwc_id]["drumsSha256"],
                "predictionSha256": sha256(raw_path),
                "referenceEventCount": len(reference),
                "predictionEventCount": len(prediction),
                "scores": {
                    str(round(tolerance * 1_000)): score_taxonomies(
                        reference, prediction, tolerance
                    )
                    for tolerance in TOLERANCES
                },
            }
        )
        tracks.append(track_result)
        print(
            json.dumps(
                {
                    "predicted": rwc_id,
                    "reference": len(reference),
                    "prediction": len(prediction),
                    "detailedF1At50ms": track_result["scores"]["50"]["detailed14"][
                        "micro"
                    ]["f1"],
                }
            ),
            flush=True,
        )

    groups: dict[str, Any] = {}
    for group_name, references_by_value in grouped_reference.items():
        groups[group_name] = {}
        for value in sorted(references_by_value):
            references = references_by_value[value]
            predictions = grouped_prediction[group_name][value]
            groups[group_name][value] = {
                "trackCount": len(references),
                "scores": aggregate_scores(references, predictions),
            }
    report = {
        "schemaVersion": 1,
        "createdAt": datetime.now(UTC).isoformat(),
        "benchmark": {
            "name": "RWC Popular 50-song full-mixture transcription benchmark",
            "status": "fresh_external_opened_test_corpus",
            "recordCount": len(tracks),
            "secondsPerTrack": manifest["tracks"][0]["clipDurationSeconds"],
            "totalScoredAudioSeconds": manifest["totalScoredAudioSeconds"],
            "referenceEventCount": manifest["referenceEventCount"],
            "inputType": "full-song mixture excerpt separated to a drum stem by Demucs",
            "referenceSource": "RWC manually controlled and time-aligned performance MIDI",
            "matcher": "one-to-one class-aware onset matching",
            "tolerancesMilliseconds": [round(value * 1_000) for value in TOLERANCES],
            "selectionFrozenBeforeInference": True,
            "selectionManifestSha256": sha256(manifest_path),
            "selectionReferenceSha256": manifest["selectionReferenceSha256"],
            "license": manifest["dataset"]["license"],
            "licenseUrl": manifest["dataset"]["licenseUrl"],
            "limitations": [
                *manifest["limitations"],
                "This scores drum-event transcription, not beat-grid quantization or engraving quality.",
                "The result includes source-separation errors and is not comparable to isolated-drum v18 scores.",
                "Demucs and this CC BY-NC corpus are research components, not the production commercial path.",
                "The corpus is now opened and must not be used to tune v18 or later reported as sealed.",
            ],
        },
        "system": {
            "name": "DrumScribe",
            "pipeline": f"{separation['model']} two-stem separation -> v18 detector",
            "modelVersion": configuration.model_version,
            "configSha256": sha256(config_path),
            "checkpointSha256": {
                name: sha256(path) for name, path in sorted(checkpoint_paths.items())
            },
            "device": device,
            "separationManifestSha256": sha256(separation_path),
        },
        "aggregate": aggregate_scores(all_reference, all_prediction),
        "groups": groups,
        "tracks": tracks,
    }
    write_json(output_path, report)
    summary = {
        "output": str(output_path),
        "device": device,
        "tracks": len(tracks),
        "seconds": manifest["totalScoredAudioSeconds"],
        "referenceEvents": manifest["referenceEventCount"],
        "detailedF1At50ms": report["aggregate"]["50"]["detailed14"]["micro"]["f1"],
        "familyF1At50ms": report["aggregate"]["50"]["family6"]["micro"]["f1"],
        "coreF1At50ms": report["aggregate"]["50"]["core3"]["micro"]["f1"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="freeze and download clips")
    prepare_parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    prepare_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    prepare_parser.add_argument("--archive-url", default=ARCHIVE_URL)
    prepare_parser.add_argument("--track-count", type=int, default=DEFAULT_TRACK_COUNT)
    prepare_parser.add_argument(
        "--selection-offset",
        type=int,
        default=0,
        help="skip this many tracks in the deterministic hash ranking",
    )
    prepare_parser.add_argument("--workers", type=int, default=4)
    prepare_parser.add_argument(
        "--window-seconds", type=float, default=DEFAULT_WINDOW_SECONDS
    )
    prepare_parser.set_defaults(handler=prepare)

    separate_parser = subparsers.add_parser(
        "separate", help="run Demucs drum isolation"
    )
    separate_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    separate_parser.add_argument("--demucs-model", default=DEFAULT_DEMUCS_MODEL)
    separate_parser.set_defaults(handler=separate)

    evaluate_parser = subparsers.add_parser("evaluate", help="run v18 and score events")
    evaluate_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    evaluate_parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    evaluate_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    evaluate_parser.add_argument(
        "--device", choices=("auto", "cpu", "mps", "cuda"), default="auto"
    )
    evaluate_parser.set_defaults(handler=evaluate)
    args = parser.parse_args()
    if getattr(args, "track_count", 1) <= 0:
        parser.error("--track-count must be positive")
    if getattr(args, "selection_offset", 0) < 0:
        parser.error("--selection-offset must not be negative")
    if getattr(args, "window_seconds", 1.0) <= 0:
        parser.error("--window-seconds must be positive")
    if getattr(args, "workers", 1) <= 0:
        parser.error("--workers must be positive")
    return args


def main() -> int:
    args = parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
