"""Atomically promote staged Dodo credentials into the live production config."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

STAGED_TO_ACTIVE = {
    "DRUMSCRIBE_DODO_LIVE_API_KEY": "DRUMSCRIBE_DODO_PAYMENTS_API_KEY",
    "DRUMSCRIBE_DODO_LIVE_WEBHOOK_KEY": "DRUMSCRIBE_DODO_PAYMENTS_WEBHOOK_KEY",
    "DRUMSCRIBE_DODO_LIVE_PRODUCT_ID": "DRUMSCRIBE_DODO_CREDIT_PACK_PRODUCT_ID",
}
STATIC_VALUES = {
    "DRUMSCRIBE_BILLING_PROVIDER": "dodo",
    "DRUMSCRIBE_DODO_PAYMENTS_ENVIRONMENT": "live_mode",
    "DRUMSCRIBE_CREDIT_PACK_SIZE": "10",
}
EXPECTED_URLS = {
    "DRUMSCRIBE_BILLING_RETURN_URL": "https://drumtoscore.com/billing/success",
    "DRUMSCRIBE_BILLING_CANCEL_URL": "https://drumtoscore.com/pricing",
}


def parse_environment(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def validate_environment(values: dict[str, str]) -> dict[str, str]:
    missing = [key for key in STAGED_TO_ACTIVE if not values.get(key)]
    if missing:
        raise ValueError(f"missing staged Dodo values: {', '.join(sorted(missing))}")

    for key in STAGED_TO_ACTIVE:
        if "\n" in values[key] or "\r" in values[key]:
            raise ValueError(f"{key} cannot contain newlines")
    if not values["DRUMSCRIBE_DODO_LIVE_PRODUCT_ID"].startswith("pdt_"):
        raise ValueError("staged Dodo product ID must start with pdt_")

    for key, expected in EXPECTED_URLS.items():
        actual = values.get(key)
        if actual != expected:
            raise ValueError(f"{key} must be {expected}")
        parsed = urlparse(actual)
        if parsed.scheme != "https" or parsed.hostname != "drumtoscore.com":
            raise ValueError(f"{key} must use the production HTTPS domain")

    updates = {
        active: values[staged] for staged, active in STAGED_TO_ACTIVE.items()
    }
    updates.update(STATIC_VALUES)
    updates.update(EXPECTED_URLS)
    return updates


def activate(path: Path) -> Path:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("production environment target must be a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise PermissionError("production environment target must have mode 0600")

    lines = path.read_text(encoding="utf-8").splitlines()
    updates = validate_environment(parse_environment(lines))
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
    backup = path.with_name(f"{path.name}.pre-dodo-live-{timestamp}")
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
        raise SystemExit("usage: activate_dodo_live_env.py ENV_FILE")
    target = Path(sys.argv[1]).resolve(strict=True)
    backup = activate(target)
    print(f"activated Dodo live mode; backup={backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
