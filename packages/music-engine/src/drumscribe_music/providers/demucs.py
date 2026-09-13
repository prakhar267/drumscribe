"""Process-isolated optional Demucs adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

from ..licensing import LicenseStatus, ProviderLicense


class DemucsAdapter:
    provider_id = "demucs-isolated-v5"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.COMMERCIAL_ALLOWED,
        code_license="MIT (Demucs code)",
        weights_license=(
            "standard upstream model terms plus separately obtained DrumScribe commercial grant"
        ),
        training_data_license=(
            "commercial inference rights covered by OWNER-ATTESTATION-2026-09-05, "
            "supplemented for htdemucs by the founder's 2026-09-13 instruction"
        ),
        attribution_required=True,
        distribution_restrictions=(
            "Commercial permission is specific to DrumScribe; retain upstream MIT notices and "
            "do not represent the separate grant as part of the public upstream license."
        ),
        decision=(
            "Self-hosted commercial inference approved by the company owner under "
            "OWNER-ATTESTATION-2026-09-05; htdemucs coverage was reaffirmed on 2026-09-13."
        ),
    )

    approved_models = frozenset({"htdemucs_ft", "htdemucs"})

    def __init__(self, *, model: str = "htdemucs_ft", python_executable: str | None = None) -> None:
        if not model or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in model
        ):
            raise ValueError("invalid Demucs model name")
        self.model = model
        self.version = model
        self.python_executable = python_executable or sys.executable
        if model not in self.approved_models:
            self.license = replace(
                type(self).license,
                status=LicenseStatus.UNRESOLVED,
                decision=(
                    f"Model {model!r} is outside OWNER-ATTESTATION-2026-09-05; "
                    "production use requires a separate approval."
                ),
            )

    def separate_drums(self, source: Path, destination: Path) -> Path:
        source = Path(source).expanduser().resolve(strict=True)
        destination = Path(destination).expanduser().resolve(strict=False)
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="drumscribe-demucs-") as directory:
            output_root = Path(directory)
            argv = (
                self.python_executable,
                "-m",
                "demucs.separate",
                "--two-stems",
                "drums",
                "--name",
                self.model,
                "--out",
                os.fspath(output_root),
                os.fspath(source),
            )
            completed = subprocess.run(argv, check=False, capture_output=True, timeout=60 * 60)
            if completed.returncode != 0:
                detail = completed.stderr.decode("utf-8", "replace").strip()[-1000:]
                raise RuntimeError(f"isolated Demucs process failed: {detail}")
            result = output_root / self.model / source.stem / "drums.wav"
            if not result.is_file():
                raise RuntimeError("Demucs completed without producing the expected drum stem")
            temporary = destination.with_name(f".{destination.name}.partial")
            if temporary.exists():
                raise FileExistsError(temporary)
            shutil.copyfile(result, temporary)
            os.link(temporary, destination)
            temporary.unlink()
        return destination


class ModalDemucsAdapter(DemucsAdapter):
    """Call the protected DrumToScore Demucs deployment on Modal."""

    provider_id = "demucs-modal-gpu-v1"
    license = replace(DemucsAdapter.license, provider_id=provider_id)

    def __init__(
        self,
        *,
        endpoint: str,
        proxy_token_id: str,
        proxy_token_secret: str,
        model: str = "htdemucs",
        timeout_seconds: float = 600,
        max_response_bytes: int = 256 * 1024 * 1024,
        ffmpeg_binary: str = "ffmpeg",
        compress_transport: bool = True,
    ) -> None:
        super().__init__(model=model)
        endpoint = endpoint.strip()
        if not endpoint.startswith(("https://", "http://localhost", "http://127.0.0.1")):
            raise ValueError("Modal Demucs endpoint must use HTTPS")
        if not proxy_token_id.strip() or not proxy_token_secret.strip():
            raise ValueError("Modal proxy credentials cannot be empty")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("Modal request limits must be positive")
        if compress_transport and not ffmpeg_binary.strip():
            raise ValueError("FFmpeg binary cannot be empty when FLAC transport is enabled")
        self.endpoint = endpoint
        self.proxy_token_id = proxy_token_id
        self._proxy_token_secret = proxy_token_secret
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.ffmpeg_binary = ffmpeg_binary
        self.compress_transport = compress_transport

    def _transcode(self, source: Path, destination: Path, *, output_format: str) -> None:
        codec_args = (
            ("-c:a", "flac", "-compression_level", "5")
            if output_format == "flac"
            else ("-c:a", "pcm_s16le", "-f", "wav")
        )
        argv = (
            self.ffmpeg_binary,
            "-nostdin",
            "-v",
            "error",
            "-i",
            os.fspath(source),
            "-map",
            "0:a:0",
            *codec_args,
            os.fspath(destination),
        )
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()[-1000:]
            raise RuntimeError(f"Modal transport conversion failed: {detail}")

    def separate_drums(self, source: Path, destination: Path) -> Path:
        source = Path(source).expanduser().resolve(strict=True)
        destination = Path(destination).expanduser().resolve(strict=False)
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        output_partial = destination.with_name(f".{destination.name}.{os.getpid()}.partial.wav")
        if output_partial.exists():
            raise FileExistsError(output_partial)
        try:
            with tempfile.TemporaryDirectory(prefix="drumtoscore-modal-transport-") as directory:
                transport_directory = Path(directory)
                request_source = source
                accept = "audio/wav"
                if self.compress_transport:
                    request_source = transport_directory / "input.flac"
                    self._transcode(source, request_source, output_format="flac")
                    accept = "audio/flac"
                request = urllib.request.Request(
                    self.endpoint,
                    data=request_source.read_bytes(),
                    method="POST",
                    headers={
                        "Accept": accept,
                        "Content-Type": "application/octet-stream",
                        "Modal-Key": self.proxy_token_id,
                        "Modal-Secret": self._proxy_token_secret,
                        "X-DrumToScore-Filename": request_source.name,
                        "X-DrumToScore-Model": self.model,
                    },
                )
                response_partial = (
                    transport_directory / "drums.flac"
                    if self.compress_transport
                    else output_partial
                )
                written = 0
                try:
                    response_context = urllib.request.urlopen(
                        request,
                        timeout=self.timeout_seconds,
                    )
                    with response_context as response, response_partial.open("xb") as handle:
                        while chunk := response.read(1024 * 1024):
                            written += len(chunk)
                            if written > self.max_response_bytes:
                                raise RuntimeError("Modal Demucs response exceeds its size limit")
                            handle.write(chunk)
                except urllib.error.HTTPError as exc:
                    detail = exc.read(2048).decode("utf-8", "replace").strip()
                    raise RuntimeError(
                        f"Modal Demucs request failed with HTTP {exc.code}: {detail}"
                    ) from exc
                except urllib.error.URLError as exc:
                    raise ConnectionError(f"Modal Demucs request failed: {exc.reason}") from exc
                if written == 0:
                    raise RuntimeError("Modal Demucs returned an empty drum stem")
                if self.compress_transport:
                    self._transcode(response_partial, output_partial, output_format="wav")
            os.link(output_partial, destination)
        finally:
            output_partial.unlink(missing_ok=True)
        return destination
