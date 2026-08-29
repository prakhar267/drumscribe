import json
import os
import subprocess
import wave
from pathlib import Path

import pytest

from drumscribe_music import (
    AudioValidationError,
    generate_waveform_peaks,
    normalize_audio,
    probe_audio,
    validate_audio,
    waveform_peaks_json,
)


def _wav(path: Path) -> Path:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
        handle.writeframes((b"\x00\x80\xff\x7f") * 400)
    return path


def test_waveform_peaks_are_bounded_and_serializable(tmp_path):
    peaks = generate_waveform_peaks(_wav(tmp_path / "fixture.wav"), bins=32)
    assert peaks.sample_rate == 8_000 and peaks.channels == 1 and len(peaks.peaks) == 32
    assert all(-1 <= low <= high <= 1 for low, high in peaks.peaks)
    assert json.loads(waveform_peaks_json(peaks))["version"] == 1


def test_waveform_rejects_empty_pcm(tmp_path):
    empty = tmp_path / "empty.wav"
    with wave.open(str(empty), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8_000)
    with pytest.raises(AudioValidationError, match="non-empty"):
        generate_waveform_peaks(empty)


def test_probe_uses_single_argv_element_for_hostile_filename(monkeypatch, tmp_path):
    source = _wav(tmp_path / "song; touch SHOULD_NOT_EXIST.wav")
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "streams": [{"codec_name": "pcm_s16le", "sample_rate": "8000", "channels": 1}],
                    "format": {
                        "format_name": "wav",
                        "duration": "0.1",
                        "size": str(source.stat().st_size),
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("drumscribe_music.audio.shutil.which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr("drumscribe_music.audio.subprocess.run", fake_run)
    metadata = probe_audio(source)
    assert metadata.codec_name == "pcm_s16le"
    assert observed["argv"][-1] == os.fspath(source.resolve())
    assert len([item for item in observed["argv"] if "touch" in item]) == 1


def test_validation_checks_declared_mime_and_actual_codec(monkeypatch, tmp_path):
    source = _wav(tmp_path / "fixture.wav")
    with pytest.raises(AudioValidationError, match="MIME"):
        validate_audio(source, declared_mime="text/plain")
    monkeypatch.setattr(
        "drumscribe_music.audio.probe_audio",
        lambda *args, **kwargs: type(
            "Metadata",
            (),
            {
                "format_name": "wav",
                "codec_name": "vorbis",
                "size_bytes": 10,
                "duration_seconds": 1.0,
            },
        )(),
    )
    with pytest.raises(AudioValidationError, match="codec"):
        validate_audio(source, declared_mime="audio/wav")

    monkeypatch.setattr(
        "drumscribe_music.audio.probe_audio",
        lambda *args, **kwargs: type(
            "Metadata",
            (),
            {
                "format_name": "mp3",
                "codec_name": "mp3",
                "size_bytes": 10,
                "duration_seconds": 1.0,
            },
        )(),
    )
    with pytest.raises(AudioValidationError, match="does not match"):
        validate_audio(source, declared_mime="audio/wav")


def test_normalize_is_argv_only_atomic_and_refuses_overwrite(monkeypatch, tmp_path):
    source = _wav(tmp_path / "a name $(unsafe).wav")
    destination = tmp_path / "normalized.wav"
    observed = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        Path(argv[-1]).write_bytes(b"RIFF" + b"\0" * 64)
        return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("drumscribe_music.audio.shutil.which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr("drumscribe_music.audio.subprocess.run", fake_run)
    assert normalize_audio(source, destination) == destination.resolve()
    assert observed["argv"][observed["argv"].index("-i") + 1] == os.fspath(source.resolve())
    with pytest.raises(FileExistsError):
        normalize_audio(source, destination)

    victim = tmp_path / "must-not-be-overwritten.txt"
    victim.write_bytes(b"keep me")
    symlink_destination = tmp_path / "symlink-output.wav"
    symlink_destination.symlink_to(victim)
    normalize_audio(source, symlink_destination, overwrite=True)
    assert victim.read_bytes() == b"keep me"
    assert not symlink_destination.is_symlink()
