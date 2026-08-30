import wave
from pathlib import Path

import mido
import pytest

from drumscribe_ml.egmd import EGMdImportError, import_egmd_dataset
from drumscribe_ml.manifest import split_payload


def _write_silent_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(8_000)
        target.writeframes(bytes(32_000))


def _write_midi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    for note in (36, 41, 54, 53):
        track.append(mido.Message("note_on", channel=9, note=note, velocity=100, time=120))
    midi.save(path)


def test_egmd_import_groups_kit_renders_and_preserves_source_split(tmp_path):
    root = tmp_path / "e-gmd"
    for variant in (1, 2):
        _write_silent_wav(root / f"drummer/session/take_{variant}.wav")
        _write_midi(root / f"drummer/session/take_{variant}.midi")
    (root / "e-gmd-v1.0.0.csv").write_text(
        "drummer,session,id,style,bpm,beat_type,time_signature,duration,split,"
        "midi_filename,audio_filename,kit_name\n"
        "drummer,drummer/session,drummer/session/take,rock,120,beat,4-4,2.0,test,"
        "drummer/session/take_1.midi,drummer/session/take_1.wav,Acoustic Kit\n"
        "drummer,drummer/session,drummer/session/take,rock,120,beat,4-4,2.0,test,"
        "drummer/session/take_2.midi,drummer/session/take_2.wav,Studio Kit\n",
        encoding="utf-8",
    )
    destination = tmp_path / "manifest.json"
    manifest = import_egmd_dataset(root, destination)
    assert len(manifest.tracks) == 2
    assert {track.group_id for track in manifest.tracks} == {"drummer/session/take"}
    annotation = (root / manifest.tracks[0].annotation_path).read_text(encoding="utf-8")
    assert all(name in annotation for name in ("KICK", "FLOOR_TOM", "TAMBOURINE", "RIDE_BELL"))
    split = split_payload(manifest, seed="ignored")
    assert split["strategy"] == "source_prescribed"
    assert len(split["assignments"]["test"]) == 2
    report = destination.with_suffix(".import-report.json").read_text(encoding="utf-8")
    assert '"performanceGroups": 1' in report


def test_egmd_import_rejects_paths_outside_the_dataset_root(tmp_path):
    root = tmp_path / "e-gmd"
    root.mkdir()
    (root / "e-gmd-v1.0.0.csv").write_text(
        "id,split,midi_filename,audio_filename,kit_name\n"
        "performance,test,../outside.midi,../outside.wav,Kit\n",
        encoding="utf-8",
    )
    with pytest.raises(EGMdImportError, match="unsafe dataset path"):
        import_egmd_dataset(root, tmp_path / "manifest.json")
