"""Import the Expanded Groove MIDI Dataset with kit-leakage protection."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .groove import (
    _canonical_split,
    _midi_events,
    _sha256,
    _wav_duration,
)
from .manifest import DatasetLicense, DatasetManifest, DatasetSource, DatasetTrack, write_manifest

EGMD_VERSION = "1.0.0"
EGMD_HOMEPAGE = "https://magenta.withgoogle.com/datasets/e-gmd"
EGMD_METADATA_NAME = "e-gmd-v1.0.0.csv"


class EGMdImportError(RuntimeError):
    pass


def import_egmd_dataset(
    dataset_root: Path,
    manifest_path: Path,
    *,
    metadata_path: Path | None = None,
    archive_path: Path | None = None,
    overwrite: bool = False,
) -> DatasetManifest:
    """Convert extracted E-GMD WAV/MIDI pairs into a governed training manifest.

    E-GMD renders the same performance with many drum kits.  Each render gets a
    unique track ID, while ``group_id`` remains the source performance ID so no
    deterministic split can leak one performance across train and test.
    """

    root = Path(dataset_root).resolve()
    metadata = Path(metadata_path).resolve() if metadata_path else root / EGMD_METADATA_NAME
    if not metadata.is_file():
        fallback = root / "info.csv"
        if fallback.is_file():
            metadata = fallback
        else:
            raise EGMdImportError(f"E-GMD metadata not found: {metadata}")

    annotation_root = root / "drumscribe-annotations"
    tracks: list[DatasetTrack] = []
    exclusions: list[dict[str, Any]] = []
    seen_track_ids: set[str] = set()
    with metadata.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"id", "split", "midi_filename", "audio_filename", "kit_name"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise EGMdImportError("E-GMD metadata is missing required columns")
        for row_number, row in enumerate(reader, start=2):
            audio_name = row["audio_filename"].strip()
            midi_name = row["midi_filename"].strip()
            performance_id = row["id"].strip()
            if not audio_name or not midi_name or not performance_id:
                raise EGMdImportError(f"E-GMD row {row_number} has empty identity fields")
            audio_path = _safe_dataset_path(root, audio_name, row_number=row_number)
            midi_path = _safe_dataset_path(root, midi_name, row_number=row_number)
            if not audio_path.is_file() or not midi_path.is_file():
                raise EGMdImportError(
                    f"missing E-GMD pair on row {row_number}: {audio_name!r}, {midi_name!r}"
                )
            track_id = Path(audio_name).with_suffix("").as_posix()
            if track_id in seen_track_ids:
                raise EGMdImportError(f"duplicate E-GMD audio identity: {track_id!r}")
            seen_track_ids.add(track_id)
            events = _midi_events(midi_path)
            audio_duration = _wav_duration(audio_path)
            beyond = [event for event in events if float(event["onsetSeconds"]) > audio_duration]
            if beyond:
                exclusions.append(
                    {
                        "id": track_id,
                        "groupId": performance_id,
                        "reason": "annotation_beyond_audio",
                        "audioDurationSeconds": audio_duration,
                        "excludedEvents": len(beyond),
                    }
                )
                continue
            annotation_path = annotation_root / Path(midi_name).with_suffix(".json")
            annotation_path.parent.mkdir(parents=True, exist_ok=True)
            annotation_path.write_text(
                json.dumps({"schemaVersion": 1, "events": events}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tracks.append(
                DatasetTrack(
                    id=track_id,
                    group_id=performance_id,
                    audio_path=audio_path.relative_to(root).as_posix(),
                    annotation_path=annotation_path.relative_to(root).as_posix(),
                    duration_seconds=audio_duration,
                    audio_sha256=_sha256(audio_path),
                    metadata={
                        "split": _canonical_split(row["split"]),
                        "kitName": row["kit_name"].strip(),
                        "drummer": row.get("drummer"),
                        "session": row.get("session"),
                        "style": row.get("style"),
                        "bpm": _optional_float(row.get("bpm")),
                        "timeSignature": row.get("time_signature"),
                        "beatType": row.get("beat_type"),
                        "performanceDurationSeconds": _optional_float(row.get("duration")),
                    },
                )
            )
    if not tracks:
        raise EGMdImportError("E-GMD import produced no valid tracks")
    manifest = DatasetManifest(
        DatasetSource(
            name="Expanded Groove MIDI Dataset",
            version=EGMD_VERSION,
            homepage=EGMD_HOMEPAGE,
            license=DatasetLicense(
                identifier="CC-BY-4.0",
                url="https://creativecommons.org/licenses/by/4.0/",
                commercial_use_allowed=True,
                derivative_works_allowed=True,
                attribution=(
                    "Google LLC; Lee Callender, Curtis Hawthorne, and Jesse Engel; "
                    "E-GMD contributing drummers"
                ),
                notes="Preserve E-GMD attribution and citation with derived model releases.",
            ),
            downloaded_at=datetime.now(UTC).isoformat(),
            archive_sha256=_sha256(Path(archive_path)) if archive_path else None,
        ),
        tuple(tracks),
    )
    write_manifest(manifest_path, manifest, overwrite=overwrite)
    manifest_path.with_suffix(".import-report.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "importedTracks": len(tracks),
                "performanceGroups": len({track.group_id for track in tracks}),
                "kitNames": sorted(
                    {
                        str(track.metadata["kitName"])
                        for track in tracks
                        if track.metadata["kitName"]
                    }
                ),
                "excludedTracks": exclusions,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise EGMdImportError(f"invalid numeric E-GMD metadata: {value!r}") from exc


def _safe_dataset_path(root: Path, value: str, *, row_number: int) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise EGMdImportError(f"E-GMD row {row_number} contains an unsafe dataset path")
    path = (root / relative).resolve()
    if root not in path.parents:
        raise EGMdImportError(f"E-GMD row {row_number} escapes the dataset root")
    return path
