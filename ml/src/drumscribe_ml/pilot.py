"""Deterministic, leakage-safe subsets for architecture pilot experiments."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class PilotDatasetError(ValueError):
    pass


def create_pilot_dataset(
    source: Path,
    destination: Path,
    *,
    seed: str,
    train_groups: int,
    validation_groups: int,
) -> Path:
    """Select complete groups from train/validation while excluding held-out test data."""
    if not seed.strip():
        raise PilotDatasetError("pilot seed must be non-empty")
    if train_groups < 1 or validation_groups < 1:
        raise PilotDatasetError("pilot group counts must be positive")

    source_path = Path(source).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if payload.get("schemaVersion") != 1 or not isinstance(records, list):
        raise PilotDatasetError("prepared dataset must use schemaVersion 1 and list records")

    by_split: dict[str, dict[str, list[dict[str, Any]]]] = {
        "train": {},
        "validation": {},
        "test": {},
    }
    group_splits: dict[str, str] = {}
    for record in records:
        try:
            split = str(record["split"])
            group_id = str(record["groupId"])
        except (KeyError, TypeError) as exc:
            raise PilotDatasetError("every prepared record needs split and groupId") from exc
        if split not in by_split or not group_id:
            raise PilotDatasetError(f"invalid prepared split or group: {split!r}/{group_id!r}")
        previous = group_splits.setdefault(group_id, split)
        if previous != split:
            raise PilotDatasetError(f"group {group_id!r} crosses prepared dataset splits")
        by_split[split].setdefault(group_id, []).append(record)

    requested = {"train": train_groups, "validation": validation_groups}
    selected_groups: dict[str, list[str]] = {}
    selected_records: list[dict[str, Any]] = []
    for split, count in requested.items():
        available = by_split[split]
        if len(available) < count:
            raise PilotDatasetError(
                f"pilot requests {count} {split} groups but only {len(available)} exist"
            )
        ranked = sorted(
            available,
            key=lambda group_id: (
                hashlib.sha256(f"{seed}\0{split}\0{group_id}".encode()).digest(),
                group_id,
            ),
        )
        selected_groups[split] = ranked[:count]
        for group_id in selected_groups[split]:
            selected_records.extend(
                sorted(
                    available[group_id],
                    key=lambda record: (
                        str(record.get("trackId", "")),
                        str(record.get("variant", "")),
                    ),
                )
            )

    pilot = {
        key: value
        for key, value in payload.items()
        if key not in {"records", "pilotSelection", "sourcePreparedDatasetSha256"}
    }
    pilot.update(
        {
            "sourcePreparedDatasetSha256": _sha256(source_path),
            "pilotSelection": {
                "strategy": "sha256_ranked_complete_groups",
                "seed": seed,
                "selectedGroups": selected_groups,
                "excludedSplits": ["test"],
            },
            "records": selected_records,
        }
    )
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(pilot, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
