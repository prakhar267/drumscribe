from __future__ import annotations

import stat
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

MODULE_SPEC = spec_from_file_location(
    "configure_neon_auth_env", Path(__file__).with_name("configure_neon_auth_env.py")
)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
configuration = module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(configuration)

BASE_URL = (
    "https://ep-spring-surf-a5ygkl98.neonauth.us-east-2.aws.neon.tech/neondb/auth"
)


def test_configure_updates_release_and_adds_auth_urls(tmp_path: Path) -> None:
    target = tmp_path / "drumscribe.env"
    target.write_text("DRUMSCRIBE_RELEASE_TAG=old\nPRESERVE=yes\n", encoding="utf-8")
    target.chmod(0o600)

    backup = configuration.configure(target, BASE_URL, "539c096")

    assert target.read_text(encoding="utf-8").splitlines() == [
        "DRUMSCRIBE_RELEASE_TAG=539c096",
        "PRESERVE=yes",
        f"DRUMSCRIBE_NEON_AUTH_BASE_URL={BASE_URL}",
        f"DRUMSCRIBE_NEON_AUTH_JWKS_URL={BASE_URL}/.well-known/jwks.json",
    ]
    assert backup.read_text(encoding="utf-8") == "DRUMSCRIBE_RELEASE_TAG=old\nPRESERVE=yes\n"
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "base_url",
    [
        "http://ep.example.neonauth.us-east-2.aws.neon.tech/neondb/auth",
        "https://example.com/neondb/auth",
        "https://ep.example.neonauth.us-east-2.aws.neon.tech/wrong",
    ],
)
def test_rejects_non_production_auth_endpoint(base_url: str) -> None:
    with pytest.raises(ValueError):
        configuration.validated_updates(base_url, "539c096")
