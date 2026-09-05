"""Process-isolated adapters for research transcription models.

The model environments intentionally live outside the API environment.  A runner
receives ``--input`` and ``--output`` arguments and must atomically write the JSON
contract validated below.  No shell is involved, and model stdout is never parsed.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar, Literal

from ..licensing import LicenseStatus, ProviderLicense
from ..mapping import canonical_instrument
from ..models import RawDrumHit

MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_HITS = 50_000
TranscriptionInputKind = Literal["full_mix", "drum_stem"]


class ExternalModelError(RuntimeError):
    """A model runner failed or violated the transcription contract."""


class ExternalModelTranscriptionProvider:
    """Strict adapter for a model-specific executable or Python runner."""

    provider_id: ClassVar[str]
    license: ClassVar[ProviderLicense]
    input_kind: ClassVar[TranscriptionInputKind] = "drum_stem"

    def __init__(
        self,
        command: Sequence[str],
        *,
        model_version: str,
        timeout_seconds: float = 1_800,
    ) -> None:
        normalized = tuple(str(item) for item in command)
        if not normalized or any(not item or "\x00" in item for item in normalized):
            raise ValueError("model command must contain non-empty argv entries")
        if not model_version.strip():
            raise ValueError("model_version must not be empty")
        if not 0 < timeout_seconds <= 14_400:
            raise ValueError("timeout_seconds must be between 0 and 14400")
        self.command = normalized
        self.version = model_version.strip()
        self.timeout_seconds = timeout_seconds

    def transcribe(self, audio_path: Path) -> list[RawDrumHit]:
        source = Path(audio_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        return self._invoke(source)

    def _invoke(
        self, source: Path, *, extra_arguments: Sequence[str] = ()
    ) -> list[RawDrumHit]:
        with tempfile.TemporaryDirectory(prefix=f"drumscribe-{self.provider_id}-") as directory:
            output = Path(directory) / "hits.json"
            argv = (
                *self.command,
                "--input",
                os.fspath(source),
                *extra_arguments,
                "--output",
                os.fspath(output),
            )
            try:
                completed = subprocess.run(
                    argv,
                    shell=False,
                    check=False,
                    timeout=self.timeout_seconds,
                    capture_output=True,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ExternalModelError(
                    f"{self.provider_id} runner could not complete: {type(exc).__name__}"
                ) from exc
            if completed.returncode != 0:
                stderr = completed.stderr.decode("utf-8", errors="replace")[-2_000:]
                raise ExternalModelError(
                    f"{self.provider_id} runner exited {completed.returncode}: {stderr}"
                )
            return self._load_result(output)

    def _load_result(self, output: Path) -> list[RawDrumHit]:
        try:
            stat = output.lstat()
        except FileNotFoundError as exc:
            raise ExternalModelError(f"{self.provider_id} runner did not create output") from exc
        if output.is_symlink() or not output.is_file():
            raise ExternalModelError("model output must be a regular file")
        if stat.st_size > MAX_RESULT_BYTES:
            raise ExternalModelError("model output exceeds the 16 MiB contract limit")
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalModelError("model output is not valid UTF-8 JSON") from exc
        if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
            raise ExternalModelError("model output must use schemaVersion 1")
        if payload.get("provider") != self.provider_id:
            raise ExternalModelError("model output provider does not match configured provider")
        hits = payload.get("hits")
        if not isinstance(hits, list) or len(hits) > MAX_HITS:
            raise ExternalModelError("model output hits must be a bounded array")
        parsed = [self._parse_hit(item, index) for index, item in enumerate(hits)]
        parsed.sort(key=lambda item: (item.onset_seconds, str(item.instrument_class)))
        return parsed

    def _parse_hit(self, item: Any, index: int) -> RawDrumHit:
        if not isinstance(item, dict):
            raise ExternalModelError(f"hit {index} must be an object")
        try:
            instrument = canonical_instrument(item["instrument"])
            onset = float(item["onsetSeconds"])
            velocity = int(item.get("velocity", 100))
            confidence = float(item.get("confidence", 0.5))
            duration = float(item.get("durationSeconds", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise ExternalModelError(f"hit {index} contains an invalid value") from exc
        if not all(math.isfinite(value) for value in (onset, confidence, duration)):
            raise ExternalModelError(f"hit {index} contains a non-finite number")
        try:
            return RawDrumHit(
                instrument,
                onset,
                velocity=velocity,
                confidence=confidence,
                duration_seconds=duration,
                metadata={"provider": self.provider_id, "modelVersion": self.version},
            )
        except (TypeError, ValueError) as exc:
            raise ExternalModelError(f"hit {index} violates the drum-hit contract") from exc


class YourMT3PlusTranscriptionProvider(ExternalModelTranscriptionProvider):
    """Full-mixture YourMT3+ A/B provider; never production enabled."""

    provider_id = "research-yourmt3-plus-v1"
    input_kind: ClassVar[TranscriptionInputKind] = "full_mix"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="conflicting upstream declarations (GPL-3.0 repository / Apache-2.0 files)",
        weights_license="not stated clearly for all distributed checkpoints",
        training_data_license="mixed research datasets; commercial rights unresolved",
        attribution_required=True,
        distribution_restrictions="Do not redistribute or production-deploy pending legal review.",
        decision="Local A/B research only.",
    )


class OaFDrumsTranscriptionProvider(ExternalModelTranscriptionProvider):
    """Onsets-and-Frames Drums baseline for isolated drum stems."""

    provider_id = "research-oaf-drums-v1"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="Apache-2.0",
        weights_license="checkpoint redistribution and commercial-use terms require review",
        training_data_license="E-GMD CC BY 4.0",
        attribution_required=True,
        distribution_restrictions="Keep in an isolated research environment until weights audit.",
        decision="Local isolated-stem A/B baseline only.",
    )


class ADTOFResearchTranscriptionProvider(ExternalModelTranscriptionProvider):
    """ADTOF adapter retained under its historical provider identifier."""

    provider_id = "research-adtof-v1"
    approved_model_version = "adtof-pytorch-85c192e78f71"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license=(
            "public upstream ADTOF is CC BY-NC-SA 4.0; DrumScribe has a separately "
            "obtained commercial grant"
        ),
        weights_license=("commercial inference rights covered by OWNER-ATTESTATION-2026-09-05"),
        training_data_license=(
            "commercial model-use rights covered by OWNER-ATTESTATION-2026-09-05"
        ),
        attribution_required=True,
        distribution_restrictions=(
            "Commercial permission is specific to DrumScribe; retain upstream attribution and "
            "do not redistribute the grant or weights beyond its scope."
        ),
        decision=(
            "Self-hosted commercial inference approved by the company owner under "
            "OWNER-ATTESTATION-2026-09-05."
        ),
    )

    def __init__(
        self,
        command: Sequence[str],
        *,
        model_version: str,
        timeout_seconds: float = 1_800,
    ) -> None:
        super().__init__(command, model_version=model_version, timeout_seconds=timeout_seconds)
        if self.version != self.approved_model_version:
            self.license = replace(
                type(self).license,
                status=LicenseStatus.UNRESOLVED,
                decision=(
                    f"Model {self.version!r} is outside OWNER-ATTESTATION-2026-09-05; "
                    "production use requires a separate approval."
                ),
            )


class DrumScribeRecallFusionTranscriptionProvider(ExternalModelTranscriptionProvider):
    """Production fusion of the approved ADTOF and first-party checkpoints."""

    provider_id = "drumscribe-recall-fusion-v2"
    approved_model_version = provider_id
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license=(
            "proprietary DrumScribe fusion; ADTOF commercial grant and upstream "
            "attributions retained"
        ),
        weights_license=(
            "first-party checkpoints plus ADTOF commercial inference rights under "
            "OWNER-ATTESTATION-2026-09-05"
        ),
        training_data_license="Groove Dataset and E-GMD CC BY 4.0",
        attribution_required=True,
        distribution_restrictions=(
            "Do not redistribute the ADTOF grant or checkpoint outside its approved scope."
        ),
        decision=(
            "Self-hosted commercial inference approved by the company owner under "
            "OWNER-ATTESTATION-2026-09-05."
        ),
    )

    def __init__(
        self,
        command: Sequence[str],
        *,
        model_version: str,
        timeout_seconds: float = 1_800,
    ) -> None:
        super().__init__(command, model_version=model_version, timeout_seconds=timeout_seconds)
        if self.version != self.approved_model_version:
            self.license = replace(
                type(self).license,
                status=LicenseStatus.UNRESOLVED,
                decision=(
                    f"Model {self.version!r} is outside OWNER-ATTESTATION-2026-09-05; "
                    "production use requires a separate approval."
                ),
            )

    def transcribe_multiview(
        self, mixture_path: Path, drum_stem_path: Path
    ) -> list[RawDrumHit]:
        mixture = Path(mixture_path).resolve()
        stem = Path(drum_stem_path).resolve()
        if not mixture.is_file():
            raise FileNotFoundError(mixture)
        if not stem.is_file():
            raise FileNotFoundError(stem)
        return self._invoke(
            stem,
            extra_arguments=("--mixture-input", os.fspath(mixture)),
        )


class DrumScribeHybridTranscriptionProvider(ExternalModelTranscriptionProvider):
    """Frozen first-party ensemble/OaF hybrid for isolated drum stems."""

    provider_id = "drumscribe-hybrid-v1"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="proprietary DrumScribe clean-room implementation",
        weights_license="first-party checkpoints; final model-card review pending",
        training_data_license="Groove Dataset and MuldjordKit-derived licensed corpora",
        attribution_required=True,
        distribution_restrictions=(
            "Research beta only until every training-data attribution and model card is approved."
        ),
        decision="Application-integrated research beta; production remains fail-closed.",
    )
