"""Process-isolated optional Demucs adapter."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ..licensing import LicenseStatus, ProviderLicense


class DemucsAdapter:
    provider_id = "demucs-isolated-v5"
    license = ProviderLicense(
        provider_id=provider_id,
        status=LicenseStatus.UNRESOLVED,
        code_license="MIT (Demucs code)",
        weights_license="model-specific; unresolved for bundled production distribution",
        training_data_license="model-specific; not sufficiently documented for our commercial gate",
        attribution_required=True,
        distribution_restrictions=(
            "Do not bundle weights until model-specific legal review is recorded."
        ),
        decision="Optional local adapter only; production gate refuses it.",
    )

    def __init__(self, *, model: str = "htdemucs_ft", python_executable: str | None = None) -> None:
        if not model or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in model
        ):
            raise ValueError("invalid Demucs model name")
        self.model = model
        self.version = model
        self.python_executable = python_executable or sys.executable

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
