"""Atomically configure Neon Auth for the Oracle production services."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse


def validated_updates(base_url: str, release_tag: str) -> dict[str, str]:
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.hostname.endswith(".neonauth.us-east-2.aws.neon.tech")
        or parsed.path != "/neondb/auth"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Neon Auth base URL must be the production HTTPS auth endpoint")
    if not release_tag or any(character not in "0123456789abcdef" for character in release_tag):
        raise ValueError("release tag must be a lowercase hexadecimal Git revision")
    return {
        "DRUMSCRIBE_NEON_AUTH_BASE_URL": base_url,
        "DRUMSCRIBE_NEON_AUTH_JWKS_URL": f"{base_url}/.well-known/jwks.json",
        "DRUMSCRIBE_RELEASE_TAG": release_tag,
    }


def configure(path: Path, base_url: str, release_tag: str) -> Path:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("production environment target must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise PermissionError("production environment target must have mode 0600")

    updates = validated_updates(base_url, release_tag)
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    rendered: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(line)
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.pre-neon-auth-{timestamp}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{path.name}.",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write("\n".join(rendered) + "\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    try:
        os.chmod(temporary_path, 0o600)
        os.chown(temporary_path, metadata.st_uid, metadata.st_gid)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return backup


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: configure_neon_auth_env.py ENV_FILE NEON_AUTH_BASE_URL RELEASE_TAG"
        )
    target = Path(sys.argv[1]).resolve(strict=True)
    backup = configure(target, sys.argv[2], sys.argv[3])
    print(f"configured Neon Auth; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
