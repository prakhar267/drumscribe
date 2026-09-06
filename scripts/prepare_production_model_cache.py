#!/usr/bin/env python3
"""Prepare the exact public model artifacts approved for the worker image."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import urllib.request
from importlib.resources import files
from pathlib import Path

ADTOF_SHA256 = "1bc986e596ec47ba0b44916f87cd4a39f0b2bec23596df3fb5d0e87749217320"
BEAT_THIS_SHA256 = "8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331"
BEAT_THIS_URL = (
    "https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt"
)
DEMUCS_REPOSITORY = "adefossez/HTDemucs-ft"
DEMUCS_SNAPSHOT = "d74ac89c3a1e874fc78f152555cf4d8533f06cd4"
DEMUCS_FILES = {
    "04573f0d.safetensors": "68854b0d7c2b3274723b5761f6fd9f5aec5f1bcd3f0de7c1669546fdb7871b7c",
    "92cfc3b6.safetensors": "a241863551f30d01c42bd7b97da40839922ead3acb0f1fcab25682f55b4eeb59",
    "d12395a8.safetensors": "5b01a97567ae9a3178a6236fb520251045c03eb8834bc8c24a4eec11d6c8fb56",
    "f7e0c4bc.safetensors": "2c85ab3c62dd6edd8e0b965e38b16fd1cdde357cc25de6b6bc9ce7c83f60925f",
    "htdemucs_ft.yaml": "69470b8c1bbd674437b51bc9fb491327a10ab0396b702c93389b9cf750016346",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"model artifact hash mismatch for {path.name}: {actual}")


def copy_adtof_weights(repository: Path) -> None:
    source = Path(
        os.fspath(
            files("adtof_pytorch") / "data" / "adtof_frame_rnn_pytorch_weights.pth"
        )
    )
    require_sha256(source, ADTOF_SHA256)
    destination = (
        repository
        / ".research-models"
        / "adtof-pytorch"
        / "data"
        / "adtof_frame_rnn_pytorch_weights.pth"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    require_sha256(destination, ADTOF_SHA256)


def download_beat_this(cache_root: Path) -> None:
    destination = cache_root / "torch" / "hub" / "checkpoints" / "beat_this-final0.ckpt"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256_file(destination) == BEAT_THIS_SHA256:
        return
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.partial")
    written = 0
    try:
        request = urllib.request.Request(
            BEAT_THIS_URL, headers={"User-Agent": "DrumScribe-build/1"}
        )
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                written += len(chunk)
                if written > 128 * 1024 * 1024:
                    raise RuntimeError(
                        "Beat This checkpoint exceeds its build-time size limit"
                    )
                handle.write(chunk)
        require_sha256(temporary, BEAT_THIS_SHA256)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_demucs(cache_root: Path) -> None:
    from huggingface_hub import hf_hub_download

    cache_dir = cache_root / "huggingface" / "hub"
    snapshot_directory: Path | None = None
    for filename, expected in DEMUCS_FILES.items():
        downloaded = Path(
            hf_hub_download(
                repo_id=DEMUCS_REPOSITORY,
                filename=filename,
                revision=DEMUCS_SNAPSHOT,
                cache_dir=cache_dir,
            )
        )
        require_sha256(downloaded, expected)
        snapshot_directory = downloaded.parent
    if snapshot_directory is None or snapshot_directory.name != DEMUCS_SNAPSHOT:
        raise RuntimeError(
            "Demucs snapshot cache was not created at the approved revision"
        )
    repository_cache = snapshot_directory.parents[1]
    reference = repository_cache / "refs" / "main"
    reference.parent.mkdir(parents=True, exist_ok=True)
    temporary = reference.with_name(f".{reference.name}.{os.getpid()}.partial")
    try:
        temporary.write_text(f"{DEMUCS_SNAPSHOT}\n", encoding="utf-8")
        temporary.replace(reference)
    finally:
        temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path("/app"))
    parser.add_argument("--cache-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repository = args.repository.expanduser().resolve(strict=True)
    cache_root = args.cache_root.expanduser().resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    copy_adtof_weights(repository)
    download_beat_this(cache_root)
    download_demucs(cache_root)
    print("production_model_cache=ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
