import json

import pytest
from drumscribe_music import Instrument

from drumscribe_ml.cli import main as ml_main
from drumscribe_ml.manifest import (
    DatasetLicense,
    DatasetManifest,
    DatasetSource,
    DatasetTrack,
    ManifestError,
    deterministic_split,
    load_manifest,
    split_payload,
    write_manifest,
)
from drumscribe_ml.mapping import map_midi_hits, map_midi_note


def _manifest(commercial=True):
    license_record = DatasetLicense(
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        commercial,
        "Example authors",
    )
    source = DatasetSource("Example", "1.0", "https://example.test/data", license_record)
    tracks = tuple(
        DatasetTrack(
            f"take-{index}",
            f"performer-{index // 2}",
            f"audio/{index}.wav",
            f"midi/{index}.mid",
            10,
        )
        for index in range(12)
    )
    return DatasetManifest(source, tracks)


def test_manifest_round_trip_and_training_gate(tmp_path):
    path = write_manifest(tmp_path / "manifest.json", _manifest())
    loaded = load_manifest(path)
    assert loaded == _manifest()
    loaded.require_training_safe()
    with pytest.raises(ManifestError, match="not approved"):
        _manifest(False).require_training_safe()


def test_split_is_deterministic_and_never_leaks_groups():
    manifest = _manifest()
    first = deterministic_split(manifest.tracks, seed="v1")
    second = deterministic_split(reversed(manifest.tracks), seed="v1")
    assert first == second
    track_split = {track_id: split for split, ids in first.items() for track_id in ids}
    for left, right in zip(manifest.tracks[::2], manifest.tracks[1::2], strict=True):
        assert track_split[left.id] == track_split[right.id]
    payload = split_payload(manifest, seed="v1")
    assert payload["seed"] == "v1" and sum(map(len, payload["assignments"].values())) == 12


def test_manifest_rejects_escaping_paths_and_bad_ratios():
    with pytest.raises(ManifestError, match="escape"):
        DatasetTrack("id", "group", "../audio.wav", "hit.mid", 1)
    with pytest.raises(ValueError, match="sum"):
        deterministic_split(_manifest().tracks, seed="x", train=0.8, validation=0.2, test=0.2)


def test_manifest_cli_validates_and_writes_split(tmp_path):
    manifest_path = write_manifest(tmp_path / "manifest.json", _manifest())
    split_path = tmp_path / "split.json"
    assert ml_main(["manifest", "validate", str(manifest_path)]) == 0
    assert (
        ml_main(
            [
                "manifest",
                "split",
                str(manifest_path),
                str(split_path),
                "--seed",
                "release-v1",
            ]
        )
        == 0
    )
    payload = json.loads(split_path.read_text())
    assert payload["seed"] == "release-v1"


def test_midi_mapping_uses_canonical_classes_and_validates_rows():
    assert map_midi_note(36) is Instrument.KICK
    mapped = map_midi_hits([(38, 0.5, 100), (46, 1.0, 80)])
    assert [hit.instrument for hit in mapped] == [Instrument.SNARE, Instrument.OPEN_HIHAT]
    with pytest.raises(ValueError, match="onset"):
        map_midi_hits([(36, -1, 100)])
