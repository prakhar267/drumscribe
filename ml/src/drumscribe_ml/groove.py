"""Import Google's commercially usable Groove MIDI Dataset into DrumScribe ML."""

from __future__ import annotations

import csv
import hashlib
import importlib
import json
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from drumscribe_music import Instrument

from .manifest import (
    DatasetLicense,
    DatasetManifest,
    DatasetSource,
    DatasetTrack,
    write_manifest,
)

GROOVE_ARCHIVE_SHA256 = "21559feb2f1c96ca53988fd4d7060b1f2afe1d854fb2a8dcea5ff95cf3cce7e9"

GROOVE_MIDI_MAP = {
    22: Instrument.CLOSED_HIHAT,
    26: Instrument.OPEN_HIHAT,
    36: Instrument.KICK,
    37: Instrument.CROSS_STICK,
    38: Instrument.SNARE,
    40: Instrument.SNARE,
    41: Instrument.FLOOR_TOM,
    42: Instrument.CLOSED_HIHAT,
    44: Instrument.PEDAL_HIHAT,
    46: Instrument.OPEN_HIHAT,
    48: Instrument.HIGH_TOM,
    50: Instrument.HIGH_TOM,
    45: Instrument.MID_TOM,
    47: Instrument.MID_TOM,
    43: Instrument.FLOOR_TOM,
    58: Instrument.FLOOR_TOM,
    49: Instrument.CRASH,
    52: Instrument.CRASH,
    55: Instrument.CRASH,
    57: Instrument.CRASH,
    51: Instrument.RIDE,
    59: Instrument.RIDE,
    53: Instrument.RIDE_BELL,
    54: Instrument.TAMBOURINE,
}


class GrooveImportError(RuntimeError):
    pass


def import_groove_dataset(
    dataset_root: Path,
    manifest_path: Path,
    *,
    archive_path: Path | None = None,
    overwrite: bool = False,
) -> DatasetManifest:
    root = Path(dataset_root).resolve()
    info_path = root / "info.csv"
    if not info_path.is_file():
        raise GrooveImportError(f"Groove metadata not found: {info_path}")
    if archive_path and _sha256(Path(archive_path)) != GROOVE_ARCHIVE_SHA256:
        raise GrooveImportError("Groove archive SHA-256 does not match Google's published digest")

    annotation_root = root / "drumscribe-annotations"
    tracks: list[DatasetTrack] = []
    excluded_tracks: list[dict[str, Any]] = []
    with info_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            audio_name = row.get("audio_filename", "").strip()
            midi_name = row.get("midi_filename", "").strip()
            if not audio_name or not midi_name:
                continue
            audio_path = root / audio_name
            midi_path = root / midi_name
            if not audio_path.is_file() or not midi_path.is_file():
                raise GrooveImportError(f"missing Groove pair: {audio_name!r}, {midi_name!r}")
            identifier = row["id"].strip()
            annotation_path = annotation_root / f"{identifier}.json"
            events = _midi_events(midi_path)
            audio_duration = _wav_duration(audio_path)
            events_beyond_audio = [
                event for event in events if float(event["onsetSeconds"]) > audio_duration
            ]
            if events_beyond_audio:
                excluded_tracks.append(
                    {
                        "id": identifier,
                        "reason": "annotation_beyond_audio",
                        "audioDurationSeconds": audio_duration,
                        "excludedEvents": len(events_beyond_audio),
                        "maximumOverrunSeconds": max(
                            float(event["onsetSeconds"]) - audio_duration
                            for event in events_beyond_audio
                        ),
                    }
                )
                continue
            annotation_path.parent.mkdir(parents=True, exist_ok=True)
            annotation_path.write_text(
                json.dumps({"schemaVersion": 1, "events": events}, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tracks.append(
                DatasetTrack(
                    id=identifier,
                    group_id=identifier,
                    audio_path=audio_path.relative_to(root).as_posix(),
                    annotation_path=annotation_path.relative_to(root).as_posix(),
                    duration_seconds=audio_duration,
                    audio_sha256=_sha256(audio_path),
                    metadata={
                        "split": _canonical_split(row.get("split", "")),
                        "drummer": row.get("drummer"),
                        "session": row.get("session"),
                        "style": row.get("style"),
                        "bpm": float(row["bpm"]),
                        "timeSignature": row.get("time_signature"),
                        "beatType": row.get("beat_type"),
                        "performanceDurationSeconds": float(row["duration"]),
                    },
                )
            )
    manifest = DatasetManifest(
        DatasetSource(
            name="Groove MIDI Dataset",
            version="1.0.0",
            homepage="https://magenta.withgoogle.com/datasets/groove",
            license=DatasetLicense(
                identifier="CC-BY-4.0",
                url="https://creativecommons.org/licenses/by/4.0/",
                commercial_use_allowed=True,
                derivative_works_allowed=True,
                attribution=(
                    "Google LLC; Jon Gillick, Adam Roberts, Jesse Engel, Douglas Eck, "
                    "and David Bamman"
                ),
                notes="Preserve attribution and the dataset citation in model documentation.",
            ),
            downloaded_at=datetime.now(UTC).isoformat(),
            archive_sha256=GROOVE_ARCHIVE_SHA256,
        ),
        tuple(tracks),
    )
    write_manifest(manifest_path, manifest, overwrite=overwrite)
    report_path = manifest_path.with_suffix(".import-report.json")
    report_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "importedTracks": len(tracks),
                "excludedTracks": excluded_tracks,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def _midi_events(path: Path) -> list[dict[str, Any]]:
    try:
        mido = importlib.import_module("mido")
    except ImportError as exc:
        raise GrooveImportError("install the 'data' extra to import Groove MIDI") from exc
    midi = mido.MidiFile(path)
    tempo = 500_000
    elapsed_seconds = 0.0
    events: list[dict[str, Any]] = []
    for message in mido.merge_tracks(midi.tracks):
        elapsed_seconds += mido.tick2second(message.time, midi.ticks_per_beat, tempo)
        if message.type == "set_tempo":
            tempo = message.tempo
        if message.type != "note_on" or message.velocity <= 0:
            continue
        instrument = GROOVE_MIDI_MAP.get(message.note)
        if instrument is None:
            continue
        events.append(
            {
                "instrument": instrument.value,
                "onsetSeconds": elapsed_seconds,
                "velocity": int(message.velocity),
                "sourceMetadata": {"midiNote": int(message.note)},
            }
        )
    return events


def _canonical_split(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized == "validation":
        return "validation"
    if normalized in {"train", "test"}:
        return normalized
    raise GrooveImportError(f"unsupported Groove split: {value!r}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return source.getnframes() / source.getframerate()
