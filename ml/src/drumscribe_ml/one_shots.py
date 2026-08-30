"""Rights-cleared one-shot catalog validation and reproducible coverage audit."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from drumscribe_music import Instrument, canonical_instrument


class OneShotCatalogError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OneShotSample:
    instrument: Instrument
    source_id: str
    path: Path
    relative_path: str
    sha256: str


def audit_one_shot_catalog(catalog_path: Path, library_root: Path) -> dict[str, Any]:
    payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("sources"), list):
        raise OneShotCatalogError("one-shot catalog must use schemaVersion 1 and list sources")
    root = Path(library_root).resolve()
    digest = hashlib.sha256()
    coverage: dict[str, dict[str, Any]] = {
        instrument.value: {"sampleCount": 0, "sources": []} for instrument in Instrument
    }
    source_reports = []
    for source in payload["sources"]:
        source_id = str(source.get("id", "")).strip()
        license_record = source.get("license")
        mappings = source.get("mappings")
        if (
            not source_id
            or not isinstance(license_record, dict)
            or not license_record.get("commercialUseAllowed")
            or not str(license_record.get("url", "")).startswith("https://")
            or not str(license_record.get("attribution", "")).strip()
            or not isinstance(mappings, list)
        ):
            raise OneShotCatalogError(
                f"source {source_id or '<unknown>'!r} lacks commercial license evidence"
            )
        source_count = 0
        for mapping in mappings:
            instrument = canonical_instrument(mapping["instrument"])
            relative = Path(str(mapping["directory"]))
            if relative.is_absolute() or ".." in relative.parts:
                raise OneShotCatalogError("sample directories must stay inside the library root")
            directory = (root / relative).resolve()
            if root not in directory.parents or not directory.is_dir():
                raise OneShotCatalogError(f"sample directory does not exist: {relative}")
            files = sorted(
                path
                for path in directory.rglob("*")
                if path.is_file() and path.suffix.casefold() in {".wav", ".flac"}
            )
            if not files:
                raise OneShotCatalogError(f"sample directory is empty: {relative}")
            for path in files:
                relative_file = path.relative_to(root).as_posix()
                file_hash = _sha256(path)
                digest.update(
                    f"{source_id}\0{instrument.value}\0{relative_file}\0{file_hash}\n".encode()
                )
            coverage_row = coverage[instrument.value]
            coverage_row["sampleCount"] += len(files)
            if source_id not in coverage_row["sources"]:
                coverage_row["sources"].append(source_id)
            source_count += len(files)
        source_reports.append(
            {
                "id": source_id,
                "sampleCount": source_count,
                "license": license_record["identifier"],
                "attribution": license_record["attribution"],
            }
        )
    required = [str(value) for value in payload.get("requiredClasses", [])]
    missing = [
        canonical_instrument(value).value
        for value in required
        if coverage[canonical_instrument(value).value]["sampleCount"] == 0
    ]
    return {
        "schemaVersion": 1,
        "catalog": str(Path(catalog_path).resolve()),
        "libraryRoot": str(root),
        "corpusSha256": digest.hexdigest(),
        "sources": source_reports,
        "coverage": coverage,
        "requiredClasses": [canonical_instrument(value).value for value in required],
        "missingRequiredClasses": sorted(set(missing)),
        "trainingReady": not missing,
    }


def one_shot_inventory(catalog_path: Path, library_root: Path) -> tuple[OneShotSample, ...]:
    """Return a licensed, deduplicated inventory after the strict catalog audit passes."""
    audit_one_shot_catalog(catalog_path, library_root)
    payload = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    root = Path(library_root).resolve()
    inventory: list[OneShotSample] = []
    assigned: dict[Path, Instrument] = {}
    for source in payload["sources"]:
        source_id = str(source["id"])
        for mapping in source["mappings"]:
            instrument = canonical_instrument(mapping["instrument"])
            directory = root / str(mapping["directory"])
            for path in sorted(
                candidate
                for candidate in directory.rglob("*")
                if candidate.is_file() and candidate.suffix.casefold() in {".wav", ".flac"}
            ):
                resolved = path.resolve()
                previous = assigned.setdefault(resolved, instrument)
                if previous != instrument:
                    raise OneShotCatalogError(
                        f"sample {resolved.relative_to(root)} maps to multiple instruments"
                    )
                if previous == instrument and any(item.path == resolved for item in inventory):
                    continue
                inventory.append(
                    OneShotSample(
                        instrument=instrument,
                        source_id=source_id,
                        path=resolved,
                        relative_path=resolved.relative_to(root).as_posix(),
                        sha256=_sha256(resolved),
                    )
                )
    return tuple(
        sorted(inventory, key=lambda item: (item.instrument.value, item.relative_path, item.sha256))
    )


def partition_one_shots(
    samples: tuple[OneShotSample, ...], *, seed: str
) -> dict[str, dict[str, tuple[OneShotSample, ...]]]:
    """Create deterministic per-class train/validation/test sound partitions."""
    if not seed.strip():
        raise OneShotCatalogError("one-shot partition seed must be non-empty")
    by_instrument: dict[str, list[OneShotSample]] = {}
    for sample in samples:
        by_instrument.setdefault(sample.instrument.value, []).append(sample)
    partitions: dict[str, dict[str, tuple[OneShotSample, ...]]] = {}
    for instrument, rows in sorted(by_instrument.items()):
        ranked = sorted(
            rows,
            key=lambda item: (
                hashlib.sha256(
                    f"{seed}\0{instrument}\0{item.relative_path}\0{item.sha256}".encode()
                ).digest(),
                item.relative_path,
            ),
        )
        if len(ranked) >= 3:
            validation_count = max(1, round(len(ranked) * 0.1))
            test_count = max(1, round(len(ranked) * 0.1))
        else:
            validation_count = test_count = 0
        train_end = len(ranked) - validation_count - test_count
        partitions[instrument] = {
            "train": tuple(ranked[:train_end]),
            "validation": tuple(ranked[train_end : train_end + validation_count]),
            "test": tuple(ranked[train_end + validation_count :]),
        }
    return partitions


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
