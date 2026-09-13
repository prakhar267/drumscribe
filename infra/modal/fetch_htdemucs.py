"""Download and verify the exact HTDemucs checkpoint used by Demucs."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import urllib.request
from pathlib import Path

CHECKPOINT_URL = (
    "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/"
    "955717e8-8726e21a.th"
)
CHECKPOINT_SHA256 = "8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
CHECKPOINT_DIRECTORY = Path("/root/.cache/torch/hub/checkpoints")
CHECKPOINT_PATH = CHECKPOINT_DIRECTORY / "955717e8-8726e21a.th"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    CHECKPOINT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="htdemucs-",
        suffix=".th",
        dir=CHECKPOINT_DIRECTORY,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urllib.request.urlopen(CHECKPOINT_URL, timeout=120) as response:
                shutil.copyfileobj(response, temporary)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        digest = sha256(temporary_path)
        if digest != CHECKPOINT_SHA256:
            raise RuntimeError("HTDemucs checkpoint hash mismatch")
        temporary_path.replace(CHECKPOINT_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
