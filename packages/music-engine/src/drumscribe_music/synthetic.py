"""Deterministic, rights-cleared synthetic demo and ground-truth generator."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import struct
import wave
from array import array
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path

from .exporters import write_midi, write_musicxml, write_pdf
from .models import DrumEvent, EventSource, GridSubdivision, Instrument
from .tempo import TempoMap


def synthetic_events(*, bars: int = 4, bpm: float = 120) -> tuple[TempoMap, list[DrumEvent]]:
    if not 1 <= bars <= 128:
        raise ValueError("bars must be between 1 and 128")
    tempo_map = TempoMap.constant(bpm)
    events: list[DrumEvent] = []
    for measure in range(bars):
        measure_start = Fraction(measure * 4)
        for eighth in range(8):
            beat = measure_start + Fraction(eighth, 2)
            instrument = (
                Instrument.OPEN_HIHAT
                if measure == bars - 1 and eighth == 7
                else Instrument.CLOSED_HIHAT
            )
            events.append(_event(tempo_map, beat, instrument, 72 + (eighth % 2) * 10))
        for beat_offset in (Fraction(0), Fraction(2)):
            beat = measure_start + beat_offset
            events.append(_event(tempo_map, beat, Instrument.KICK, 108))
        for beat_offset in (Fraction(1), Fraction(3)):
            beat = measure_start + beat_offset
            events.append(_event(tempo_map, beat, Instrument.SNARE, 112))
        if measure == 0:
            events.append(_event(tempo_map, measure_start, Instrument.CRASH, 118))
    return tempo_map, sorted(
        events, key=lambda event: (event.onset_seconds, event.instrument.value)
    )


def generate_synthetic_demo(
    output_directory: Path, *, bars: int = 4, bpm: float = 120, sample_rate: int = 44_100
) -> dict[str, str | int | float]:
    output = Path(output_directory).expanduser().resolve(strict=False)
    output.mkdir(parents=True, exist_ok=True)
    known = [
        "synthetic-demo.wav",
        "ground-truth.json",
        "ground-truth.mid",
        "ground-truth.musicxml",
        "ground-truth.pdf",
        "manifest.json",
    ]
    existing = [name for name in known if (output / name).exists()]
    if existing:
        raise FileExistsError(f"refusing to overwrite generated files: {', '.join(existing)}")
    tempo_map, events = synthetic_events(bars=bars, bpm=bpm)
    wav_path = output / "synthetic-demo.wav"
    _render_wav(wav_path, events, tempo_map, bars=bars, sample_rate=sample_rate)
    event_path = output / "ground-truth.json"
    event_payload = {
        "schemaVersion": 1,
        "rights": "Generated entirely by DrumScribe code; no third-party recording or sample used.",
        "tempoMap": {"bpm": bpm, "timeSignature": "4/4"},
        "events": [event.as_dict() for event in events],
    }
    event_path.write_text(
        json.dumps(event_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_midi(output / "ground-truth.mid", events, tempo_map)
    write_musicxml(output / "ground-truth.musicxml", events, tempo_map, title="Synthetic Groove")
    write_pdf(output / "ground-truth.pdf", events, tempo_map, title="Synthetic Groove")
    assets = {}
    for name in known[:-1]:
        path = output / name
        assets[name] = {"bytes": path.stat().st_size, "sha256": _sha256(path)}
    manifest = {
        "schemaVersion": 1,
        "generator": "drumscribe_music.synthetic",
        "seed": 17,
        "bars": bars,
        "bpm": bpm,
        "sampleRate": sample_rate,
        "rightsCleared": True,
        "assets": assets,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"output": str(output), "bars": bars, "bpm": bpm, "events": len(events)}


def _event(tempo_map: TempoMap, beat: Fraction, instrument: Instrument, velocity: int) -> DrumEvent:
    position = tempo_map.beat_to_position(beat)
    subdivision = GridSubdivision.EIGHTH if beat.denominator == 2 else GridSubdivision.QUARTER
    return DrumEvent(
        id=f"synthetic-{beat.numerator}-{beat.denominator}-{instrument.value.lower()}",
        instrument=instrument,
        onset_seconds=tempo_map.beat_to_seconds(beat),
        velocity=velocity,
        confidence=1,
        source=EventSource.SYNTHETIC,
        beat_position=beat,
        measure_index=position.measure_index,
        beat_in_measure=position.beat_in_measure,
        subdivision=subdivision,
        quantized_onset_seconds=tempo_map.beat_to_seconds(beat),
        created_at=datetime(2000, 1, 1, tzinfo=UTC),
        updated_at=datetime(2000, 1, 1, tzinfo=UTC),
    )


def _render_wav(
    destination: Path,
    events: list[DrumEvent],
    tempo_map: TempoMap,
    *,
    bars: int,
    sample_rate: int,
) -> None:
    duration = tempo_map.beat_to_seconds(Fraction(bars * 4)) + 0.75
    sample_count = math.ceil(duration * sample_rate)
    samples = array("f", [0.0]) * sample_count
    random_source = random.Random(17)
    for event in events:
        start = round(event.onset_seconds * sample_rate)
        amplitude = event.velocity / 127 * 0.72
        if event.instrument is Instrument.KICK:
            length = int(sample_rate * 0.32)
            phase = 0.0
            for index in range(min(length, sample_count - start)):
                time = index / sample_rate
                frequency = 92 * math.exp(-time * 10) + 42
                phase += 2 * math.pi * frequency / sample_rate
                samples[start + index] += amplitude * math.sin(phase) * math.exp(-time * 13)
        elif event.instrument is Instrument.SNARE:
            length = int(sample_rate * 0.18)
            for index in range(min(length, sample_count - start)):
                time = index / sample_rate
                noise = random_source.uniform(-1, 1)
                tone = math.sin(2 * math.pi * 185 * time)
                samples[start + index] += (
                    amplitude * (noise * 0.75 + tone * 0.25) * math.exp(-time * 22)
                )
        else:
            length = int(
                sample_rate
                * (0.45 if event.instrument in (Instrument.CRASH, Instrument.OPEN_HIHAT) else 0.08)
            )
            previous = 0.0
            for index in range(min(length, sample_count - start)):
                time = index / sample_rate
                noise = random_source.uniform(-1, 1)
                high = noise - previous * 0.92
                previous = noise
                decay = 7 if event.instrument in (Instrument.CRASH, Instrument.OPEN_HIHAT) else 45
                samples[start + index] += amplitude * high * 0.38 * math.exp(-time * decay)
    # Quiet generated bass notes make this a full-mix-like fixture while remaining rights-cleared.
    for beat in range(bars * 4):
        start = round(tempo_map.beat_to_seconds(beat) * sample_rate)
        length = int(sample_rate * 0.38)
        frequency = (55.0, 65.41, 73.42, 49.0)[(beat // 4) % 4]
        for index in range(min(length, sample_count - start)):
            time = index / sample_rate
            samples[start + index] += (
                0.09 * math.sin(2 * math.pi * frequency * time) * math.exp(-time * 4)
            )
    peak = max(1.0, max(abs(value) for value in samples) / 0.96)
    with wave.open(str(destination), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        chunk_size = 8192
        for start in range(0, len(samples), chunk_size):
            chunk = samples[start : start + chunk_size]
            handle.writeframesraw(
                struct.pack(
                    f"<{len(chunk)}h",
                    *(round(max(-1, min(1, value / peak)) * 32767) for value in chunk),
                )
            )
        handle.writeframes(b"")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bars", type=int, default=4)
    parser.add_argument("--bpm", type=float, default=120)
    parser.add_argument("--sample-rate", type=int, default=44_100)
    args = parser.parse_args(argv)
    result = generate_synthetic_demo(
        args.output, bars=args.bars, bpm=args.bpm, sample_rate=args.sample_rate
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
