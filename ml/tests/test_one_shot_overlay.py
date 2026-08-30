import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import soundfile

from drumscribe_ml.lifecycle import PreparationConfig, cache_log_mel, read_pcm_wav, write_pcm_wav
from drumscribe_ml.one_shot_overlay import (
    OneShotOverlayConfig,
    OneShotOverlayError,
    create_one_shot_overlays,
    create_one_shot_probe,
)
from drumscribe_ml.one_shots import one_shot_inventory, partition_one_shots


def _write_audio(path: Path, *, sample_rate: int, channels: int, frequency: float) -> None:
    timeline = np.arange(sample_rate * 2, dtype=np.float32) / sample_rate
    mono = np.sin(2 * np.pi * frequency * timeline).astype(np.float32) * 0.1
    samples = np.repeat(mono[:, None], channels, axis=1)
    write_pcm_wav(path, samples, sample_rate)


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    preparation = PreparationConfig(
        seed="fixture",
        sample_rate=8_000,
        frame_length=256,
        hop_length=80,
        mel_bands=24,
        augmentation_variants=0,
    )
    records = []
    for index, split in enumerate(("train", "validation", "test")):
        audio = tmp_path / "source" / f"{split}.wav"
        annotation = tmp_path / "source" / f"{split}.json"
        feature = tmp_path / "source" / f"{split}.npz"
        _write_audio(audio, sample_rate=8_000, channels=2, frequency=110 + index * 20)
        annotation.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "events": [
                        {
                            "instrument": "KICK",
                            "onsetSeconds": 0.5,
                            "velocity": 100,
                            "originalLabel": "36",
                            "sourceMetadata": {},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        cache_log_mel(audio, feature, preparation)
        records.append(
            {
                "trackId": split,
                "groupId": f"group-{split}",
                "split": split,
                "variant": "original",
                "audioPath": str(audio),
                "annotationPath": str(annotation),
                "featurePath": str(feature),
                "durationSeconds": 2.0,
            }
        )
    prepared = tmp_path / "prepared.json"
    prepared.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "dataset": {"name": "fixture", "version": "1"},
                "datasetManifestHash": "fixture-hash",
                "configuration": asdict(preparation),
                "records": records,
            }
        ),
        encoding="utf-8",
    )

    library = tmp_path / "library"
    sources = []
    for instrument, directory, frequency in (
        ("LOW_TOM", "low-tom", 90),
        ("TAMBOURINE", "tambourine", 900),
    ):
        sample_directory = library / directory
        sample_directory.mkdir(parents=True)
        for sample_index in range(5):
            timeline = np.arange(2_205, dtype=np.float32) / 11_025
            decay = np.exp(-timeline * 12)
            sample = (np.sin(2 * np.pi * (frequency + sample_index) * timeline) * decay).astype(
                np.float32
            )
            soundfile.write(sample_directory / f"{sample_index}.flac", sample, 11_025)
        sources.append(
            {
                "id": f"fixture-{instrument.lower()}",
                "license": {
                    "identifier": "CC0-1.0",
                    "url": "https://creativecommons.org/publicdomain/zero/1.0/",
                    "commercialUseAllowed": True,
                    "attribution": "Generated test fixture",
                },
                "mappings": [{"instrument": instrument, "directory": directory}],
            }
        )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "requiredClasses": ["LOW_TOM", "TAMBOURINE"],
                "sources": sources,
            }
        ),
        encoding="utf-8",
    )
    return prepared, catalog, library


def test_overlays_are_deterministic_training_only_and_use_partitioned_samples(tmp_path):
    prepared, catalog, library = _fixture(tmp_path)
    config = OneShotOverlayConfig(seed="overlay-v1", hits_per_class=1)
    first = create_one_shot_overlays(prepared, catalog, library, tmp_path / "first", config=config)
    second = create_one_shot_overlays(
        prepared, catalog, library, tmp_path / "second", config=config
    )
    source_payload = json.loads(prepared.read_text())
    first_payload = json.loads(first.read_text())
    second_payload = json.loads(second.read_text())

    assert first_payload["records"][:3] == source_payload["records"]
    assert len(first_payload["records"]) == 4
    generated = first_payload["records"][-1]
    repeated = second_payload["records"][-1]
    assert generated["split"] == "train"
    assert generated["groupId"] == "group-train"
    assert generated["audioSha256"] == repeated["audioSha256"]
    assert generated["augmentation"] == repeated["augmentation"]
    assert first_payload["oneShotOverlay"]["untouchedSplits"] == ["validation", "test"]
    assert first_payload["oneShotOverlay"]["generatedEventCounts"] == {
        "LOW_TOM": 1,
        "TAMBOURINE": 1,
    }

    events = json.loads(Path(generated["annotationPath"]).read_text())["events"]
    assert {event["instrument"] for event in events} == {"KICK", "LOW_TOM", "TAMBOURINE"}
    overlay_events = [event for event in events if event["sourceMetadata"].get("syntheticOverlay")]
    inventory = one_shot_inventory(catalog, library)
    partitions = partition_one_shots(inventory, seed=config.seed)
    training_paths = {
        sample.relative_path
        for instrument in ("LOW_TOM", "TAMBOURINE")
        for sample in partitions[instrument]["train"]
    }
    held_out_paths = {
        sample.relative_path
        for instrument in ("LOW_TOM", "TAMBOURINE")
        for partition in ("validation", "test")
        for sample in partitions[instrument][partition]
    }
    assert training_paths.isdisjoint(held_out_paths)
    assert {event["sourceMetadata"]["sampleRelativePath"] for event in overlay_events} <= (
        training_paths
    )

    original_audio, _ = read_pcm_wav(Path(source_payload["records"][0]["audioPath"]))
    augmented_audio, _ = read_pcm_wav(Path(generated["audioPath"]))
    assert not np.array_equal(original_audio, augmented_audio)
    assert np.load(generated["featurePath"])["features"].shape[1] == 24

    with pytest.raises(OneShotOverlayError, match="already contains"):
        create_one_shot_overlays(first, catalog, library, tmp_path / "duplicate", config=config)


def test_probe_uses_only_source_validation_and_reserved_validation_samples(tmp_path):
    prepared, catalog, library = _fixture(tmp_path)
    config = OneShotOverlayConfig(seed="probe-v1", hits_per_class=1)
    probe = create_one_shot_probe(prepared, catalog, library, tmp_path / "probe", config=config)
    payload = json.loads(probe.read_text())
    assert payload["evaluationOnly"] is True
    assert payload["oneShotProbe"]["sourceSplit"] == "validation"
    assert payload["oneShotProbe"]["excludedSourceSplits"] == ["train", "test"]
    assert len(payload["records"]) == 1
    assert payload["records"][0]["split"] == "probe"

    events = json.loads(Path(payload["records"][0]["annotationPath"]).read_text())["events"]
    overlay_events = [event for event in events if event["sourceMetadata"].get("syntheticOverlay")]
    assert len(overlay_events) == 2
    assert {event["sourceMetadata"]["partition"] for event in overlay_events} == {"validation"}
    partitions = partition_one_shots(one_shot_inventory(catalog, library), seed=config.seed)
    validation_paths = {
        sample.relative_path
        for instrument in ("LOW_TOM", "TAMBOURINE")
        for sample in partitions[instrument]["validation"]
    }
    assert {event["sourceMetadata"]["sampleRelativePath"] for event in overlay_events} <= (
        validation_paths
    )
