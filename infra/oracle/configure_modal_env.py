"""Atomically configure the protected Modal separator in a production env file."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

MAPPING = {
    "endpoint": "DRUMSCRIBE_MODAL_DEMUCS_ENDPOINT",
    "token_id": "DRUMSCRIBE_MODAL_PROXY_TOKEN_ID",
    "token_secret": "DRUMSCRIBE_MODAL_PROXY_TOKEN_SECRET",
    "release_tag": "DRUMSCRIBE_RELEASE_TAG",
}
STATIC_VALUES = {
    "DRUMSCRIBE_SOURCE_SEPARATION_PROVIDER": "demucs",
    "DRUMSCRIBE_DEMUCS_MODEL": "htdemucs",
    "DRUMSCRIBE_MODAL_MAX_RESPONSE_BYTES": "268435456",
}


def validated_payload() -> dict[str, str]:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict) or set(payload) != set(MAPPING):
        raise ValueError("input must contain endpoint, token_id, and token_secret")
    if not all(isinstance(value, str) and value for value in payload.values()):
        raise ValueError("Modal configuration values must be non-empty strings")
    if any("\n" in value or "\r" in value for value in payload.values()):
        raise ValueError("Modal configuration values cannot contain newlines")
    if not payload["endpoint"].startswith("https://"):
        raise ValueError("Modal endpoint must use HTTPS")
    if not payload["token_id"].startswith("wk-"):
        raise ValueError("Modal proxy token ID must start with wk-")
    if not payload["token_secret"].startswith("ws-"):
        raise ValueError("Modal proxy token secret must start with ws-")
    if not re.fullmatch(r"[0-9a-f]{7,40}", payload["release_tag"]):
        raise ValueError("release tag must be a 7-40 character Git commit hash")
    return payload


def update_environment(path: Path, payload: dict[str, str]) -> Path:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("production environment target must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise PermissionError("production environment target must have mode 0600")

    updates = {MAPPING[key]: value for key, value in payload.items()}
    updates.update(STATIC_VALUES)
    seen: set[str] = set()
    rendered: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, _ = line.partition("=")
        if separator and key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(line)
    for key, value in updates.items():
        if key not in seen:
            rendered.append(f"{key}={value}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # noqa: UP017
    backup = path.with_name(f"{path.name}.pre-modal-{timestamp}")
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
    if len(sys.argv) != 2:
        raise SystemExit("usage: configure_modal_env.py ENV_FILE")
    target = Path(sys.argv[1]).resolve(strict=True)
    backup = update_environment(target, validated_payload())
    print(f"configured Modal separator; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
