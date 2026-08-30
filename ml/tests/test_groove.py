import wave
from pathlib import Path

import mido

from drumscribe_ml.groove import import_groove_dataset
from drumscribe_ml.manifest import load_manifest, split_payload


def _write_silent_wav(path: Path) -> None:
    path.parent.mkdir(parents=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(8_000)
        target.writeframes(bytes(16_000))


def test_groove_import_maps_extended_kit_and_preserves_official_split(tmp_path):
    root = tmp_path / "groove"
    audio = root / "take.wav"
    midi_path = root / "take.mid"
    _write_silent_wav(audio)
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=500_000, time=0))
    for note in (36, 22, 53, 58):
        track.append(mido.Message("note_on", channel=9, note=note, velocity=100, time=120))
    midi.save(midi_path)
    (root / "info.csv").write_text(
        "drummer,session,id,style,bpm,beat_type,time_signature,midi_filename,"
        "audio_filename,duration,split\n"
        "drummer1,session1,take,rock,120,beat,4-4,take.mid,take.wav,1.0,test\n",
        encoding="utf-8",
    )

    destination = tmp_path / "manifest.json"
    manifest = import_groove_dataset(root, destination)
    assert load_manifest(destination) == manifest
    assert manifest.source.license.commercial_use_allowed
    annotation = (root / manifest.tracks[0].annotation_path).read_text(encoding="utf-8")
    assert all(name in annotation for name in ("KICK", "CLOSED_HIHAT", "RIDE_BELL", "FLOOR_TOM"))
    split = split_payload(manifest, seed="ignored")
    assert split["strategy"] == "source_prescribed"
    assert split["assignments"]["test"] == ["take"]
    assert '"excludedTracks": []' in destination.with_suffix(".import-report.json").read_text()
