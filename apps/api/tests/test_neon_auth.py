from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from drumscribe_api.config import Settings
from drumscribe_api.errors import APIError
from drumscribe_api.services import neon_auth


class StaticJwksClient:
    def __init__(self, public_key) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _token: str):
        return SimpleNamespace(key=self.public_key)


def make_token(private_key, issuer: str, **overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": "neon-user-1",
        "email": "Drummer@Example.com",
        "emailVerified": True,
        "iss": issuer,
        "aud": issuer,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": "test-key"})


@pytest.mark.asyncio
async def test_verify_neon_identity_validates_signature_and_normalizes_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    settings = Settings(neon_auth_base_url="https://auth.example.com/neondb/auth")
    monkeypatch.setattr(
        neon_auth,
        "_jwks_client",
        lambda _url: StaticJwksClient(private_key.public_key()),
    )

    identity = await neon_auth.verify_neon_identity(
        make_token(private_key, settings.neon_auth_issuer or ""),
        settings,
    )

    assert identity.subject == "neon-user-1"
    assert identity.email == "drummer@example.com"


@pytest.mark.asyncio
async def test_verify_neon_identity_rejects_wrong_audience(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    settings = Settings(neon_auth_base_url="https://auth.example.com/neondb/auth")
    monkeypatch.setattr(
        neon_auth,
        "_jwks_client",
        lambda _url: StaticJwksClient(private_key.public_key()),
    )

    with pytest.raises(APIError) as exc_info:
        await neon_auth.verify_neon_identity(
            make_token(private_key, settings.neon_auth_issuer or "", aud="https://attacker.test"),
            settings,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "NEON_TOKEN_INVALID"


@pytest.mark.asyncio
async def test_verify_neon_identity_requires_verified_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    settings = Settings(neon_auth_base_url="https://auth.example.com/neondb/auth")
    monkeypatch.setattr(
        neon_auth,
        "_jwks_client",
        lambda _url: StaticJwksClient(private_key.public_key()),
    )

    with pytest.raises(APIError) as exc_info:
        await neon_auth.verify_neon_identity(
            make_token(private_key, settings.neon_auth_issuer or "", emailVerified=False),
            settings,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "EMAIL_NOT_VERIFIED"
