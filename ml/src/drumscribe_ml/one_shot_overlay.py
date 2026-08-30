"""Deterministic training-only overlays from rights-cleared one-shot samples."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile
from drumscribe_music import Instrument, canonical_instrument

from .lifecycle import PreparationConfig, cache_log_mel, read_pcm_wav, sha256_file, write_pcm_wav
from .one_shots import (
    OneShotSample,
    audit_one_shot_catalog,
    one_shot_inventory,
    partition_one_shots,
)


class OneShotOverlayError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OneShotOverlayConfig:
    seed: str
    classes: tuple[str, ...] = ("LOW_TOM", "TAMBOURINE")
    variants_per_record: int = 1
    hits_per_class: int = 1
    record_limit: int | None = None
    minimum_spacing_seconds: float = 0.3
    avoid_existing_seconds: float = 0.08
    maximum_sample_seconds: float = 2.0
    minimum_gain_db: float = -18.0
    maximum_gain_db: float = -8.0

    def __post_init__(self) -> None:
        if not self.seed.strip() or not self.classes:
            raise OneShotOverlayError("overlay seed and at least one class are required")
        if self.variants_per_record < 1 or self.hits_per_class < 1:
            raise OneShotOverlayError("overlay variant and hit counts must be positive")
        if self.record_limit is not None and self.record_limit < 1:
            raise OneShotOverlayError("overlay record limit must be positive when provided")
        if self.minimum_spacing_seconds <= 0 or self.avoid_existing_seconds < 0:
            raise OneShotOverlayError("overlay spacing values are invalid")
        if self.maximum_sample_seconds <= 0:
            raise OneShotOverlayError("maximum sample duration must be positive")
        if self.minimum_gain_db > self.maximum_gain_db or self.maximum_gain_db > 0:
            raise OneShotOverlayError("overlay gain range must be ordered and no louder than 0 dB")
        canonical = [canonical_instrument(value).value for value in self.classes]
        if len(canonical) != len(set(canonical)):
            raise OneShotOverlayError("overlay classes must be unique")


def create_one_shot_overlays(
    prepared_dataset: Path,
    catalog_path: Path,
    library_root: Path,
    output_root: Path,
    *,
    config: OneShotOverlayConfig,
) -> Path:
    """Append synthetic variants to training groups without changing validation/test records."""
    source_path = Path(prepared_dataset).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if payload.get("schemaVersion") != 1 or not isinstance(records, list):
        raise OneShotOverlayError("prepared dataset must use schemaVersion 1 and list records")
    if payload.get("oneShotOverlay"):
        raise OneShotOverlayError("prepared dataset already contains one-shot overlays")
    preparation_payload = payload.get("configuration")
    if not isinstance(preparation_payload, dict):
        raise OneShotOverlayError("prepared dataset is missing its feature configuration")
    preparation = PreparationConfig(**preparation_payload)

    audit = audit_one_shot_catalog(catalog_path, library_root)
    inventory = one_shot_inventory(catalog_path, library_root)
    partitions = partition_one_shots(inventory, seed=config.seed)
    instruments = tuple(canonical_instrument(value) for value in config.classes)
    train_samples = {
        instrument: partitions.get(instrument.value, {}).get("train", ())
        for instrument in instruments
    }
    missing = [instrument.value for instrument, rows in train_samples.items() if not rows]
    if missing:
        raise OneShotOverlayError(f"no training-partition samples for: {', '.join(missing)}")

    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    generated: list[dict[str, Any]] = []
    generated_counts = {instrument.value: 0 for instrument in instruments}
    source_records = _selected_original_records(
        records, split="train", seed=config.seed, limit=config.record_limit
    )
    for record in source_records:
        for variant in range(1, config.variants_per_record + 1):
            augmented, counts = _overlay_record(
                record,
                output,
                preparation,
                config,
                variant,
                instruments,
                train_samples,
                audit["corpusSha256"],
            )
            generated.append(augmented)
            for instrument, count in counts.items():
                generated_counts[instrument] += count

    if not generated:
        raise OneShotOverlayError("prepared dataset contains no original training records")
    result = dict(payload)
    result["sourcePreparedDatasetSha256"] = _sha256(source_path)
    result["oneShotOverlay"] = {
        "schemaVersion": 1,
        "configuration": asdict(config),
        "corpusSha256": audit["corpusSha256"],
        "sources": audit["sources"],
        "samplePartitions": {
            instrument.value: {
                name: {
                    "count": len(rows),
                    "sha256": _partition_hash(rows),
                }
                for name, rows in partitions[instrument.value].items()
            }
            for instrument in instruments
        },
        "generatedRecords": len(generated),
        "selectedSourceGroups": len({str(record["groupId"]) for record in source_records}),
        "generatedEventCounts": generated_counts,
        "untouchedSplits": ["validation", "test"],
    }
    result["records"] = [*records, *generated]
    destination = output / "prepared-dataset.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def create_one_shot_probe(
    prepared_dataset: Path,
    catalog_path: Path,
    library_root: Path,
    output_root: Path,
    *,
    config: OneShotOverlayConfig,
) -> Path:
    """Build an evaluation-only probe from validation audio and reserved validation sounds."""
    source_path = Path(prepared_dataset).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if payload.get("schemaVersion") != 1 or not isinstance(records, list):
        raise OneShotOverlayError("prepared dataset must use schemaVersion 1 and list records")
    preparation_payload = payload.get("configuration")
    if not isinstance(preparation_payload, dict):
        raise OneShotOverlayError("prepared dataset is missing its feature configuration")
    preparation = PreparationConfig(**preparation_payload)
    audit = audit_one_shot_catalog(catalog_path, library_root)
    partitions = partition_one_shots(
        one_shot_inventory(catalog_path, library_root), seed=config.seed
    )
    instruments = tuple(canonical_instrument(value) for value in config.classes)
    probe_samples = {
        instrument: partitions.get(instrument.value, {}).get("validation", ())
        for instrument in instruments
    }
    missing = [instrument.value for instrument, rows in probe_samples.items() if not rows]
    if missing:
        raise OneShotOverlayError(f"no validation-partition samples for: {', '.join(missing)}")

    source_records = _selected_original_records(
        records, split="validation", seed=config.seed, limit=config.record_limit
    )
    output = Path(output_root).resolve()
    output.mkdir(parents=True, exist_ok=False)
    generated: list[dict[str, Any]] = []
    generated_counts = {instrument.value: 0 for instrument in instruments}
    for record in source_records:
        augmented, counts = _overlay_record(
            record,
            output,
            preparation,
            config,
            1,
            instruments,
            probe_samples,
            audit["corpusSha256"],
            sample_partition="validation",
            output_split="probe",
            variant_prefix="one-shot-probe",
        )
        generated.append(augmented)
        for instrument, count in counts.items():
            generated_counts[instrument] += count
    if not generated:
        raise OneShotOverlayError("prepared dataset contains no original validation records")

    result = {
        "schemaVersion": 1,
        "evaluationOnly": True,
        "dataset": payload.get("dataset"),
        "datasetManifestHash": payload.get("datasetManifestHash"),
        "sourcePreparedDatasetSha256": _sha256(source_path),
        "configuration": preparation_payload,
        "oneShotProbe": {
            "schemaVersion": 1,
            "configuration": asdict(config),
            "corpusSha256": audit["corpusSha256"],
            "sources": audit["sources"],
            "samplePartition": "validation",
            "samplePartitionHashes": {
                instrument.value: _partition_hash(partitions[instrument.value]["validation"])
                for instrument in instruments
            },
            "reservedTestPartitionHashes": {
                instrument.value: _partition_hash(partitions[instrument.value]["test"])
                for instrument in instruments
            },
            "generatedRecords": len(generated),
            "generatedEventCounts": generated_counts,
            "sourceSplit": "validation",
            "excludedSourceSplits": ["train", "test"],
        },
        "records": generated,
    }
    destination = output / "prepared-probe.json"
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _overlay_record(
    record: dict[str, Any],
    output: Path,
    preparation: PreparationConfig,
    config: OneShotOverlayConfig,
    variant: int,
    instruments: tuple[Instrument, ...],
    train_samples: dict[Instrument, tuple[OneShotSample, ...]],
    corpus_sha256: str,
    *,
    sample_partition: str = "train",
    output_split: str = "train",
    variant_prefix: str = "one-shot",
) -> tuple[dict[str, Any], dict[str, int]]:
    track_id = str(record["trackId"])
    audio, sample_rate = read_pcm_wav(Path(record["audioPath"]))
    annotation = json.loads(Path(record["annotationPath"]).read_text(encoding="utf-8"))
    events = list(annotation.get("events", []))
    occupied = [float(event["onsetSeconds"]) for event in events]
    duration = len(audio) / sample_rate
    rng = _rng(config.seed, track_id, str(variant))
    requests = [instrument for instrument in instruments for _ in range(config.hits_per_class)]
    rng.shuffle(requests)
    positions = _choose_positions(duration, occupied, len(requests), config, rng)
    if len(positions) != len(requests):
        raise OneShotOverlayError(
            f"track {track_id!r} is too short for {len(requests)} collision-safe overlays"
        )

    overlay_events: list[dict[str, Any]] = []
    counts = {instrument.value: 0 for instrument in instruments}
    for instrument, onset in zip(requests, positions, strict=True):
        sample = rng.choice(train_samples[instrument])
        one_shot = _load_one_shot(
            sample.path,
            target_sample_rate=sample_rate,
            target_channels=audio.shape[1],
            maximum_seconds=config.maximum_sample_seconds,
        )
        gain_db = rng.uniform(config.minimum_gain_db, config.maximum_gain_db)
        one_shot *= 10 ** (gain_db / 20)
        start = round(onset * sample_rate)
        length = min(len(one_shot), len(audio) - start)
        audio[start : start + length] += one_shot[:length]
        velocity = round(
            64
            + (gain_db - config.minimum_gain_db)
            * 55
            / max(config.maximum_gain_db - config.minimum_gain_db, 1e-9)
        )
        metadata = {
            "syntheticOverlay": True,
            "sourceId": sample.source_id,
            "sampleRelativePath": sample.relative_path,
            "sampleSha256": sample.sha256,
            "partition": sample_partition,
            "gainDb": gain_db,
        }
        event = {
            "instrument": instrument.value,
            "onsetSeconds": onset,
            "velocity": min(127, max(1, velocity)),
            "originalLabel": instrument.value,
            "sourceMetadata": metadata,
        }
        events.append(event)
        overlay_events.append(event)
        counts[instrument.value] += 1

    peak = float(np.max(np.abs(audio)))
    if peak > 0.98:
        audio *= 0.98 / peak
    relative = Path(track_id) / f"{variant_prefix}-{variant}"
    audio_path = output / "augmented" / relative.with_suffix(".wav")
    annotation_path = output / "canonical" / relative.with_suffix(".json")
    feature_path = output / "features" / relative.with_suffix(".npz")
    write_pcm_wav(audio_path, audio, sample_rate)
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "events": sorted(
                    events, key=lambda item: (item["onsetSeconds"], item["instrument"])
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    cache_log_mel(audio_path, feature_path, preparation)
    return (
        {
            "trackId": track_id,
            "groupId": str(record["groupId"]),
            "split": output_split,
            "variant": f"{variant_prefix}-{variant}",
            "audioPath": str(audio_path),
            "audioSha256": sha256_file(audio_path),
            "annotationPath": str(annotation_path),
            "featurePath": str(feature_path),
            "augmentation": {
                "kind": (
                    "rights-cleared-one-shot-overlay"
                    if output_split == "train"
                    else "rights-cleared-one-shot-probe"
                ),
                "seed": config.seed,
                "corpusSha256": corpus_sha256,
                "events": overlay_events,
            },
            "durationSeconds": duration,
        },
        counts,
    )


def _selected_original_records(
    records: list[dict[str, Any]], *, split: str, seed: str, limit: int | None
) -> list[dict[str, Any]]:
    eligible = [
        record
        for record in records
        if record.get("split") == split and record.get("variant") == "original"
    ]
    ranked = sorted(
        eligible,
        key=lambda record: (
            hashlib.sha256(
                f"{seed}\0{record.get('groupId', '')}\0{record.get('trackId', '')}".encode()
            ).digest(),
            str(record.get("trackId", "")),
        ),
    )
    return ranked if limit is None else ranked[:limit]


def _choose_positions(
    duration: float,
    occupied: list[float],
    count: int,
    config: OneShotOverlayConfig,
    rng: random.Random,
) -> list[float]:
    candidates = [
        round(value, 3) for value in np.arange(0.25, max(0.25, duration - 0.1), 0.05).tolist()
    ]
    preferred = [
        value
        for value in candidates
        if all(abs(value - existing) >= config.avoid_existing_seconds for existing in occupied)
    ]
    preferred_set = set(preferred)
    fallback = [value for value in candidates if value not in preferred_set]
    rng.shuffle(preferred)
    rng.shuffle(fallback)
    selected: list[float] = []
    for candidate in [*preferred, *fallback]:
        if all(
            abs(candidate - existing) >= config.minimum_spacing_seconds for existing in selected
        ):
            selected.append(candidate)
            if len(selected) == count:
                break
    return selected


def _load_one_shot(
    path: Path,
    *,
    target_sample_rate: int,
    target_channels: int,
    maximum_seconds: float,
) -> np.ndarray:
    samples, sample_rate = soundfile.read(path, dtype="float32", always_2d=True)
    if not len(samples) or not np.isfinite(samples).all():
        raise OneShotOverlayError(f"one-shot sample is empty or invalid: {path}")
    envelope = np.max(np.abs(samples), axis=1)
    peak = float(envelope.max())
    if peak <= 1e-6:
        raise OneShotOverlayError(f"one-shot sample is silent: {path}")
    active = np.flatnonzero(envelope >= max(1e-4, peak * 0.01))
    samples = samples[int(active[0]) :]
    if sample_rate != target_sample_rate:
        output_length = max(1, round(len(samples) * target_sample_rate / sample_rate))
        source_x = np.arange(len(samples))
        target_x = np.linspace(0, len(samples) - 1, output_length)
        samples = np.column_stack(
            [
                np.interp(target_x, source_x, samples[:, channel])
                for channel in range(samples.shape[1])
            ]
        ).astype(np.float32)
    if target_channels == 1:
        samples = samples.mean(axis=1, keepdims=True)
    elif target_channels == 2 and samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    elif target_channels == 2 and samples.shape[1] > 2:
        samples = samples[:, :2]
    elif target_channels not in {1, 2}:
        raise OneShotOverlayError("target audio must be mono or stereo")
    samples = samples[: max(1, round(maximum_seconds * target_sample_rate))]
    samples /= max(float(np.max(np.abs(samples))), 1e-6)
    fade = min(len(samples), max(1, round(target_sample_rate * 0.02)))
    samples[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)[:, None]
    return samples.astype(np.float32)


def _rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("\0".join(parts).encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _partition_hash(rows: tuple[OneShotSample, ...]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row.instrument.value}\0{row.relative_path}\0{row.sha256}\n".encode())
    return digest.hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
