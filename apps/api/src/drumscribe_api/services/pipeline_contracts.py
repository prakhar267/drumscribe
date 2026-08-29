from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..enums import Instrument


@dataclass(frozen=True, slots=True)
class RawDrumHit:
    instrument: Instrument
    onset_seconds: float
    velocity: int
    confidence: float


@dataclass(frozen=True, slots=True)
class BeatAnalysis:
    tempo_bpm: float
    beat_positions_seconds: tuple[float, ...]
    downbeat_positions_seconds: tuple[float, ...]
    time_signature_numerator: int = 4
    time_signature_denominator: int = 4
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class QuantizedHit:
    raw: RawDrumHit
    beat_position: float
    measure_index: int
    subdivision: str
    quantized_onset: float


@runtime_checkable
class SourceSeparationProvider(Protocol):
    name: str
    version: str

    async def separate_drums(self, source: Path, destination: Path) -> None: ...


@runtime_checkable
class DrumTranscriptionProvider(Protocol):
    name: str
    version: str

    async def transcribe(self, drum_audio: Path) -> list[RawDrumHit]: ...


@runtime_checkable
class BeatTrackingProvider(Protocol):
    name: str
    version: str

    async def analyze(self, audio: Path) -> BeatAnalysis: ...


@runtime_checkable
class QuantizationProvider(Protocol):
    name: str
    version: str

    async def quantize(
        self, hits: list[RawDrumHit], beat_analysis: BeatAnalysis
    ) -> list[QuantizedHit]: ...


@runtime_checkable
class NotationGenerator(Protocol):
    name: str
    version: str

    async def generate_musicxml(self, events: list[QuantizedHit], title: str) -> bytes: ...

