"""Versioned dataset manifests and leakage-resistant deterministic splits."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DatasetLicense:
    identifier: str
    url: str
    commercial_use_allowed: bool
    attribution: str
    derivative_works_allowed: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.identifier.strip() or not self.url.startswith("https://"):
            raise ManifestError("dataset license requires an identifier and HTTPS source URL")
        if not self.attribution.strip():
            raise ManifestError("dataset attribution must be recorded")
        if not isinstance(self.commercial_use_allowed, bool) or not isinstance(
            self.derivative_works_allowed, bool
        ):
            raise ManifestError("dataset license permissions must be booleans")


@dataclass(frozen=True, slots=True)
class DatasetSource:
    name: str
    version: str
    homepage: str
    license: DatasetLicense
    downloaded_at: str | None = None
    archive_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ManifestError("dataset source name and version are required")
        if not self.homepage.startswith("https://"):
            raise ManifestError("dataset homepage must use HTTPS")
        if self.archive_sha256 and (
            len(self.archive_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.archive_sha256.lower())
        ):
            raise ManifestError("archive_sha256 must be a 64-character hexadecimal digest")


@dataclass(frozen=True, slots=True)
class DatasetTrack:
    id: str
    group_id: str
    audio_path: str
    annotation_path: str
    duration_seconds: float
    audio_sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.group_id.strip():
            raise ManifestError("track id and group_id are required")
        if Path(self.audio_path).is_absolute() or Path(self.annotation_path).is_absolute():
            raise ManifestError("dataset paths must be relative for reproducibility")
        if ".." in Path(self.audio_path).parts or ".." in Path(self.annotation_path).parts:
            raise ManifestError("dataset paths may not escape their dataset root")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds <= 0:
            raise ManifestError("track duration must be positive and finite")
        if self.audio_sha256 and (
            len(self.audio_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.audio_sha256.lower())
        ):
            raise ManifestError("audio_sha256 must be a 64-character hexadecimal digest")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    source: DatasetSource
    tracks: tuple[DatasetTrack, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ManifestError(f"unsupported manifest schema version: {self.schema_version}")
        identifiers = [track.id for track in self.tracks]
        if len(identifiers) != len(set(identifiers)):
            raise ManifestError("track ids must be unique")

    def require_training_safe(self) -> None:
        license_record = self.source.license
        if not license_record.commercial_use_allowed:
            raise ManifestError(
                f"dataset {self.source.name!r} is not approved for commercial model training"
            )
        if not license_record.derivative_works_allowed:
            raise ManifestError(
                f"dataset {self.source.name!r} does not allow the required derivative work"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "source": {
                "name": self.source.name,
                "version": self.source.version,
                "homepage": self.source.homepage,
                "downloadedAt": self.source.downloaded_at,
                "archiveSha256": self.source.archive_sha256,
                "license": {
                    "identifier": self.source.license.identifier,
                    "url": self.source.license.url,
                    "commercialUseAllowed": self.source.license.commercial_use_allowed,
                    "derivativeWorksAllowed": self.source.license.derivative_works_allowed,
                    "attribution": self.source.license.attribution,
                    "notes": self.source.license.notes,
                },
            },
            "tracks": [
                {
                    "id": track.id,
                    "groupId": track.group_id,
                    "audioPath": track.audio_path,
                    "annotationPath": track.annotation_path,
                    "durationSeconds": track.duration_seconds,
                    "audioSha256": track.audio_sha256,
                    "metadata": dict(track.metadata),
                }
                for track in self.tracks
            ],
        }


def load_manifest(path: Path) -> DatasetManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        source_data = payload["source"]
        license_data = source_data["license"]
        source = DatasetSource(
            name=source_data["name"],
            version=source_data["version"],
            homepage=source_data["homepage"],
            downloaded_at=source_data.get("downloadedAt"),
            archive_sha256=source_data.get("archiveSha256"),
            license=DatasetLicense(
                identifier=license_data["identifier"],
                url=license_data["url"],
                commercial_use_allowed=license_data["commercialUseAllowed"],
                derivative_works_allowed=license_data.get("derivativeWorksAllowed", True),
                attribution=license_data["attribution"],
                notes=license_data.get("notes", ""),
            ),
        )
        tracks = tuple(
            DatasetTrack(
                id=item["id"],
                group_id=item["groupId"],
                audio_path=item["audioPath"],
                annotation_path=item["annotationPath"],
                duration_seconds=item["durationSeconds"],
                audio_sha256=item.get("audioSha256"),
                metadata=item.get("metadata", {}),
            )
            for item in payload["tracks"]
        )
        return DatasetManifest(source, tracks, payload.get("schemaVersion", 1))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"invalid dataset manifest: {exc}") from exc


def write_manifest(path: Path, manifest: DatasetManifest, *, overwrite: bool = False) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with destination.open(mode, encoding="utf-8") as handle:
        json.dump(manifest.as_dict(), handle, indent=2, sort_keys=True)
        handle.write("\n")
    return destination


def deterministic_split(
    tracks: Iterable[DatasetTrack],
    *,
    seed: str,
    train: float = 0.8,
    validation: float = 0.1,
    test: float = 0.1,
) -> dict[str, list[str]]:
    ratios = (train, validation, test)
    if any(not math.isfinite(value) or value < 0 for value in ratios):
        raise ValueError("split ratios must be finite and non-negative")
    if not math.isclose(sum(ratios), 1.0, rel_tol=0, abs_tol=1e-9):
        raise ValueError("split ratios must sum to 1")
    by_group: dict[str, list[DatasetTrack]] = {}
    for track in tracks:
        by_group.setdefault(track.group_id, []).append(track)
    result = {"train": [], "validation": [], "test": []}
    train_cutoff = train
    validation_cutoff = train + validation
    for group_id in sorted(by_group):
        digest = hashlib.sha256(f"{seed}\0{group_id}".encode()).digest()
        value = int.from_bytes(digest[:8], "big") / 2**64
        split = (
            "train"
            if value < train_cutoff
            else "validation"
            if value < validation_cutoff
            else "test"
        )
        result[split].extend(
            track.id for track in sorted(by_group[group_id], key=lambda item: item.id)
        )
    return result


def split_payload(
    manifest: DatasetManifest,
    *,
    seed: str,
    train: float = 0.8,
    validation: float = 0.1,
    test: float = 0.1,
) -> dict[str, Any]:
    manifest.require_training_safe()
    assignments = deterministic_split(
        manifest.tracks, seed=seed, train=train, validation=validation, test=test
    )
    return {
        "schemaVersion": 1,
        "source": {"name": manifest.source.name, "version": manifest.source.version},
        "seed": seed,
        "ratios": {"train": train, "validation": validation, "test": test},
        "assignments": assignments,
    }
