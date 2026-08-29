"""Licensed, reproducible dataset preparation and audio feature caching."""

from __future__ import annotations

import hashlib
import json
import math
import random
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from drumscribe_music import canonical_instrument

from .manifest import DatasetManifest, DatasetTrack, split_payload


class PreparationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PreparationConfig:
    seed: str
    sample_rate: int = 22_050
    frame_length: int = 1_024
    hop_length: int = 220
    mel_bands: int = 80
    augmentation_variants: int = 2

    def __post_init__(self) -> None:
        if not self.seed.strip():
            raise PreparationError("a non-empty preparation seed is required")
        if self.sample_rate < 8_000 or self.frame_length < 128 or self.hop_length < 1:
            raise PreparationError("invalid audio feature configuration")
        if not 8 <= self.mel_bands <= 256 or not 0 <= self.augmentation_variants <= 32:
            raise PreparationError("invalid mel-band or augmentation count")


@dataclass(frozen=True, slots=True)
class AugmentationRecipe:
    seed: int
    gain_db: float
    compression_drive: float
    room_mix: float
    noise_db: float
    low_shelf_db: float
    high_shelf_db: float
    bandwidth_scale: float
    stereo_width: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_track(track: DatasetTrack, dataset_root: Path) -> dict[str, Any]:
    audio = dataset_root / track.audio_path
    annotation = dataset_root / track.annotation_path
    if not audio.is_file() or not annotation.is_file():
        raise PreparationError(f"track {track.id!r} is missing audio or annotation data")
    digest = sha256_file(audio)
    if track.audio_sha256 and digest != track.audio_sha256.lower():
        raise PreparationError(f"track {track.id!r} audio checksum does not match its manifest")
    with wave.open(str(audio), "rb") as source:
        if source.getsampwidth() != 2:
            raise PreparationError("preparation currently requires normalized 16-bit PCM WAV input")
        measured_duration = source.getnframes() / source.getframerate()
    tolerance = max(0.1, track.duration_seconds * 0.01)
    if abs(measured_duration - track.duration_seconds) > tolerance:
        raise PreparationError(f"track {track.id!r} duration does not match its manifest")
    return {
        "trackId": track.id,
        "audioPath": track.audio_path,
        "annotationPath": track.annotation_path,
        "audioSha256": digest,
        "durationSeconds": measured_duration,
    }


def canonicalize_annotation(source: Path, destination: Path, *, duration: float) -> Path:
    payload = json.loads(Path(source).read_text(encoding="utf-8"))
    rows = payload.get("events") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise PreparationError("annotations must be an event array or an object with events")
    output: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PreparationError("every annotation event must be an object")
        original = row.get("instrument", row.get("midiNote", row.get("label")))
        onset = float(row["onsetSeconds"])
        velocity = int(row.get("velocity", 100))
        if not math.isfinite(onset) or not 0 <= onset <= duration or not 1 <= velocity <= 127:
            raise PreparationError("annotation onset or velocity is outside the track bounds")
        output.append(
            {
                "instrument": canonical_instrument(original).value,
                "onsetSeconds": onset,
                "velocity": velocity,
                "originalLabel": str(original),
                "sourceMetadata": row.get("sourceMetadata", {}),
            }
        )
    output.sort(key=lambda item: (item["onsetSeconds"], item["instrument"]))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"schemaVersion": 1, "events": output}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


def augmentation_recipe(seed: str, track_id: str, variant: int) -> AugmentationRecipe:
    if variant < 1:
        raise PreparationError("augmentation variants are one-based")
    digest = hashlib.sha256(f"{seed}\0{track_id}\0{variant}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    return AugmentationRecipe(
        seed=int.from_bytes(digest[:8], "big"),
        gain_db=rng.uniform(-6, 4),
        compression_drive=rng.uniform(1, 2.5),
        room_mix=rng.uniform(0, 0.14),
        noise_db=rng.uniform(-52, -34),
        low_shelf_db=rng.uniform(-3, 3),
        high_shelf_db=rng.uniform(-4, 2),
        bandwidth_scale=rng.uniform(0.62, 1.0),
        stereo_width=rng.uniform(0.65, 1.25),
    )


def read_pcm_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as source:
        channels = source.getnchannels()
        sample_rate = source.getframerate()
        if source.getsampwidth() != 2 or channels not in {1, 2}:
            raise PreparationError("audio must be mono or stereo 16-bit PCM WAV")
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2")
    return samples.reshape(-1, channels).astype(np.float32) / 32768.0, sample_rate


def write_pcm_wav(path: Path, samples: np.ndarray, sample_rate: int) -> Path:
    normalized = np.clip(samples, -1, 1)
    encoded = (normalized * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(encoded.shape[1])
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(encoded.tobytes())
    return path


def augment_wav(source: Path, destination: Path, recipe: AugmentationRecipe) -> Path:
    """Apply repeatable, bounded mix-domain augmentation to a normalized WAV."""
    samples, sample_rate = read_pcm_wav(source)
    rng = np.random.default_rng(recipe.seed)
    samples = samples * (10 ** (recipe.gain_db / 20))
    samples = np.tanh(samples * recipe.compression_drive) / np.tanh(recipe.compression_drive)

    spectrum = np.fft.rfft(samples, axis=0)
    frequencies = np.linspace(0, 1, spectrum.shape[0], dtype=np.float32)
    low = (1 - frequencies) ** 2 * recipe.low_shelf_db
    high = frequencies**2 * recipe.high_shelf_db
    cutoff = max(0.05, recipe.bandwidth_scale)
    rolloff = np.where(frequencies <= cutoff, 1, np.exp(-10 * (frequencies - cutoff)))
    spectrum *= (10 ** ((low + high) / 20) * rolloff)[:, None]
    samples = np.fft.irfft(spectrum, n=len(samples), axis=0).astype(np.float32)

    delay = max(1, int(sample_rate * 0.037))
    if recipe.room_mix and len(samples) > delay:
        samples[delay:] += samples[:-delay] * recipe.room_mix
    noise_level = 10 ** (recipe.noise_db / 20)
    samples += rng.normal(0, noise_level, size=samples.shape).astype(np.float32)
    if samples.shape[1] == 2:
        mid = (samples[:, 0] + samples[:, 1]) / 2
        side = (samples[:, 0] - samples[:, 1]) / 2 * recipe.stereo_width
        samples = np.column_stack((mid + side, mid - side))
    peak = float(np.max(np.abs(samples)))
    if peak > 0.98:
        samples *= 0.98 / peak
    return write_pcm_wav(destination, samples, sample_rate)


def cache_log_mel(source: Path, destination: Path, config: PreparationConfig) -> Path:
    samples, sample_rate = read_pcm_wav(source)
    mono = samples.mean(axis=1)
    if sample_rate != config.sample_rate:
        output_length = max(1, round(len(mono) * config.sample_rate / sample_rate))
        mono = np.interp(
            np.linspace(0, len(mono) - 1, output_length),
            np.arange(len(mono)),
            mono,
        ).astype(np.float32)
    if len(mono) < config.frame_length:
        mono = np.pad(mono, (0, config.frame_length - len(mono)))
    frame_count = 1 + (len(mono) - config.frame_length) // config.hop_length
    frames = np.lib.stride_tricks.sliding_window_view(mono, config.frame_length)[
        : frame_count * config.hop_length : config.hop_length
    ]
    power = np.abs(np.fft.rfft(frames * np.hanning(config.frame_length), axis=1)) ** 2
    filters = _mel_filterbank(config.sample_rate, config.frame_length, config.mel_bands)
    features = np.log1p(power @ filters.T).astype(np.float32)
    destination.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        destination,
        features=features,
        sample_rate=np.array(config.sample_rate),
        hop_length=np.array(config.hop_length),
        source_sha256=np.array(sha256_file(source)),
    )
    return destination


def _mel_filterbank(sample_rate: int, frame_length: int, bands: int) -> np.ndarray:
    def hz_to_mel(value: np.ndarray | float) -> np.ndarray:
        return 2595 * np.log10(1 + np.asarray(value) / 700)

    def mel_to_hz(value: np.ndarray) -> np.ndarray:
        return 700 * (10 ** (value / 2595) - 1)

    mel_points = np.linspace(hz_to_mel(20), hz_to_mel(sample_rate / 2), bands + 2)
    bins = np.floor((frame_length + 1) * mel_to_hz(mel_points) / sample_rate).astype(int)
    maximum = frame_length // 2
    filters = np.zeros((bands, maximum + 1), dtype=np.float32)
    for band in range(bands):
        left, center, right = np.clip(bins[band : band + 3], 0, maximum)
        if center > left:
            filters[band, left:center] = np.arange(center - left) / (center - left)
        if right > center:
            filters[band, center:right] = (right - np.arange(center, right)) / (right - center)
    return filters


def prepare_dataset(
    manifest: DatasetManifest,
    *,
    dataset_root: Path,
    output_root: Path,
    config: PreparationConfig,
) -> Path:
    """Run validated → canonicalized → split → augmented → feature-cache stages."""
    manifest.require_training_safe()
    output_root.mkdir(parents=True, exist_ok=True)
    split = split_payload(manifest, seed=config.seed)
    track_split = {
        track_id: name
        for name, identifiers in split["assignments"].items()
        for track_id in identifiers
    }
    records: list[dict[str, Any]] = []
    for track in manifest.tracks:
        validation = validate_track(track, dataset_root)
        canonical_path = output_root / "canonical" / f"{track.id}.json"
        canonicalize_annotation(
            dataset_root / track.annotation_path,
            canonical_path,
            duration=validation["durationSeconds"],
        )
        sources = [("original", dataset_root / track.audio_path, None)]
        for variant in range(1, config.augmentation_variants + 1):
            recipe = augmentation_recipe(config.seed, track.id, variant)
            augmented = output_root / "augmented" / track.id / f"variant-{variant}.wav"
            augment_wav(dataset_root / track.audio_path, augmented, recipe)
            sources.append((f"variant-{variant}", augmented, asdict(recipe)))
        for variant_name, audio_path, recipe_payload in sources:
            cache_path = output_root / "features" / track.id / f"{variant_name}.npz"
            cache_log_mel(audio_path, cache_path, config)
            records.append(
                {
                    "trackId": track.id,
                    "groupId": track.group_id,
                    "split": track_split[track.id],
                    "variant": variant_name,
                    "audioPath": str(audio_path.resolve()),
                    "audioSha256": sha256_file(audio_path),
                    "annotationPath": str(canonical_path.resolve()),
                    "featurePath": str(cache_path.resolve()),
                    "augmentation": recipe_payload,
                    "durationSeconds": validation["durationSeconds"],
                }
            )
    payload = {
        "schemaVersion": 1,
        "dataset": {"name": manifest.source.name, "version": manifest.source.version},
        "datasetManifestHash": hashlib.sha256(
            json.dumps(manifest.as_dict(), sort_keys=True).encode()
        ).hexdigest(),
        "configuration": asdict(config),
        "split": split,
        "records": records,
    }
    destination = output_root / "prepared-dataset.json"
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination
