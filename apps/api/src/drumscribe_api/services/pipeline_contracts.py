from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..enums import Instrument


class ProviderCategory(StrEnum):
    """Deployment trust boundary for every audio-analysis provider."""

    PRODUCTION_COMMERCIAL = "PRODUCTION_COMMERCIAL"
    DEVELOPMENT_RESEARCH = "DEVELOPMENT_RESEARCH"
    TEST_FIXTURE = "TEST_FIXTURE"


class ProviderErrorCategory(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    BAD_INPUT = "BAD_INPUT"
    RATE_LIMIT = "RATE_LIMIT"
    TIMEOUT = "TIMEOUT"
    UPSTREAM_FAILURE = "UPSTREAM_FAILURE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    DOWNLOAD_FAILURE = "DOWNLOAD_FAILURE"


@dataclass(frozen=True, slots=True)
class ProviderRunMetadata:
    provider: str
    category: ProviderCategory
    model_version: str
    request_id: str | None
    processing_ms: int
    confidence: float | None = None
    error_category: ProviderErrorCategory | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)
    cost_amount: float | None = None
    cost_currency: str | None = None
    retention_expires_at: str | None = None
    contract_reference: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "category": self.category.value,
            "modelVersion": self.model_version,
            "requestId": self.request_id,
            "processingMs": self.processing_ms,
            "confidence": self.confidence,
            "errorCategory": self.error_category.value if self.error_category else None,
            "rawMetadata": self.raw_metadata,
            "cost": (
                {"amount": self.cost_amount, "currency": self.cost_currency}
                if self.cost_amount is not None
                else None
            ),
            "retentionExpiresAt": self.retention_expires_at,
            "contractReference": self.contract_reference,
        }


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
class SeparatedAudioResult:
    drum_audio: Path
    metadata: ProviderRunMetadata
    optional_other_assets: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class DrumTranscriptionResult:
    hits: tuple[RawDrumHit, ...]
    metadata: ProviderRunMetadata


@dataclass(frozen=True, slots=True)
class Beat:
    time_seconds: float
    beat_in_measure: int
    measure_index: int
    is_downbeat: bool
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class TempoSegment:
    start_seconds: float
    bpm: float
    time_signature_numerator: int
    time_signature_denominator: int
    start_measure: int


@dataclass(frozen=True, slots=True)
class BeatTrackingResult:
    segments: tuple[TempoSegment, ...]
    beats: tuple[Beat, ...]
    bar_one_seconds: float
    metadata: ProviderRunMetadata


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
