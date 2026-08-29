import hashlib
import json
import wave

from drumscribe_music.synthetic import generate_synthetic_demo, main


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_demo_is_rights_cleared_complete_and_deterministic(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    result = generate_synthetic_demo(first, bars=2, bpm=100, sample_rate=8_000)
    generate_synthetic_demo(second, bars=2, bpm=100, sample_rate=8_000)
    assert result["events"] > 20
    expected = {
        "synthetic-demo.wav",
        "ground-truth.json",
        "ground-truth.mid",
        "ground-truth.musicxml",
        "ground-truth.pdf",
        "manifest.json",
    }
    assert {path.name for path in first.iterdir()} == expected
    for name in expected - {"manifest.json"}:
        assert _digest(first / name) == _digest(second / name)
    manifest = json.loads((first / "manifest.json").read_text())
    assert manifest["rightsCleared"] is True and manifest["seed"] == 17
    with wave.open(str(first / "synthetic-demo.wav"), "rb") as audio:
        assert audio.getframerate() == 8_000 and audio.getnchannels() == 1


def test_synthetic_cli_generates_assets(tmp_path):
    output = tmp_path / "cli"
    assert main([str(output), "--bars", "1", "--bpm", "110", "--sample-rate", "8000"]) == 0
    assert (output / "manifest.json").is_file()
