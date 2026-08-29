"""Deterministic providers for tests and local end-to-end development."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from ..licensing import LicenseStatus, ProviderLicense
from ..models import RawDrumHit
from ..tempo import TempoMap


class MockDrumTranscriptionProvider:
    provider_id = "mock"
    license = ProviderLicense(
        provider_id="mock",
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license="project code",
        decision="Safe deterministic fixture provider; never represented as AI transcription.",
    )

    def __init__(self, hits: Iterable[RawDrumHit] = ()) -> None:
        self._hits = tuple(hits)

    def transcribe(self, audio_path: Path) -> list[RawDrumHit]:
        if not Path(audio_path).is_file():
            raise FileNotFoundError(audio_path)
        return list(self._hits)


class MockBeatTrackingProvider:
    provider_id = "mock-beat-tracker"
    license = ProviderLicense(
        provider_id="mock-beat-tracker",
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license="project code",
        decision="Safe deterministic fixture provider.",
    )

    def __init__(self, tempo_map: TempoMap | None = None) -> None:
        self.tempo_map = tempo_map or TempoMap.constant()

    def track(self, audio_path: Path) -> TempoMap:
        if not Path(audio_path).is_file():
            raise FileNotFoundError(audio_path)
        return self.tempo_map


class PassthroughSourceSeparationProvider:
    """A fixture adapter that copies audio; it never claims to isolate drums."""

    provider_id = "passthrough"
    license = ProviderLicense(
        provider_id="passthrough",
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license="project code",
        decision="Safe no-op fixture provider.",
    )

    def separate_drums(self, source: Path, destination: Path) -> Path:
        source, destination = Path(source), Path(destination)
        if not source.is_file():
            raise FileNotFoundError(source)
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination
