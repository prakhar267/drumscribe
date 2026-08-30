import importlib.util
from pathlib import Path

import mido


def _contract_module():
    path = Path(__file__).resolve().parents[2] / "scripts/model_runners/_midi_contract.py"
    spec = importlib.util.spec_from_file_location("drumscribe_midi_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_mix_converter_only_accepts_general_midi_drum_channel(tmp_path):
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.Message("note_on", channel=0, note=36, velocity=100, time=0))
    track.append(mido.Message("note_on", channel=9, note=38, velocity=110, time=120))
    path = tmp_path / "mixture.mid"
    midi.save(path)
    hits = _contract_module().midi_hits(path)
    assert [(hit["instrument"], hit["velocity"]) for hit in hits] == [("SNARE", 110)]
