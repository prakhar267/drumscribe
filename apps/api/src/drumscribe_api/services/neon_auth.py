import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
import structlog
from jwt import PyJWKClient

from ..config import Settings
from ..errors import APIError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NeonIdentity:
    subject: str
    email: str


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> PyJWKClient:
    # PyJWKClient caches a successfully fetched key set and refreshes on key rotation.
    return PyJWKClient(url, cache_jwk_set=True, lifespan=300)


def _decode(token: str, settings: Settings) -> dict[str, Any]:
    jwks_url = settings.neon_auth_jwks_endpoint
    issuer = settings.neon_auth_issuer
    if not jwks_url or not issuer:
        raise APIError(503, "AUTH_PROVIDER_UNAVAILABLE", "Account sign-in is not configured.")
    signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["EdDSA"],
        issuer=issuer,
        audience=issuer,
        options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
    )


async def verify_neon_identity(token: str, settings: Settings) -> NeonIdentity:
    if not token or len(token) > 16_384:
        raise APIError(401, "NEON_TOKEN_INVALID", "The account sign-in could not be verified.")
    try:
        claims = await asyncio.to_thread(_decode, token, settings)
    except APIError:
        raise
    except (jwt.PyJWTError, ValueError) as exc:
        logger.warning(
            "neon_auth_token_rejected",
            error_type=type(exc).__name__,
            reason=str(exc),
        )
        raise APIError(
            401,
            "NEON_TOKEN_INVALID",
            "The account sign-in could not be verified.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    email_verified = claims.get("emailVerified", claims.get("email_verified"))
    email = claims.get("email")
    subject = claims.get("sub")
    if email_verified is not True or not isinstance(email, str) or not isinstance(subject, str):
        raise APIError(
            401,
            "EMAIL_NOT_VERIFIED",
            "Verify your email address before continuing.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    normalized = email.strip().casefold()
    if not normalized or len(normalized) > 320 or "@" not in normalized:
        raise APIError(401, "NEON_TOKEN_INVALID", "The account email could not be verified.")
    return NeonIdentity(subject=subject, email=normalized)
