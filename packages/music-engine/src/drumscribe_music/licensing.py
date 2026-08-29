"""Fail-closed provider licensing policy for production startup."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class LicenseStatus(StrEnum):
    COMMERCIAL_ALLOWED = "commercial_allowed"
    NON_COMMERCIAL = "non_commercial"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ProviderLicense:
    provider_id: str
    status: LicenseStatus
    code_license: str
    weights_license: str = "not applicable"
    training_data_license: str = "not applicable"
    attribution_required: bool = False
    distribution_restrictions: str = "none known"
    decision: str = ""


class LicensedProvider(Protocol):
    provider_id: str
    license: ProviderLicense


class UnsafeProviderError(RuntimeError):
    pass


def require_production_safe(provider: LicensedProvider, *, production: bool = True) -> None:
    """Refuse every provider that is not explicitly cleared for commercial use."""

    if not production:
        return
    license_record = provider.license
    if license_record.provider_id != provider.provider_id:
        raise UnsafeProviderError("provider identity does not match its license record")
    if license_record.status is not LicenseStatus.COMMERCIAL_ALLOWED:
        raise UnsafeProviderError(
            f"provider {provider.provider_id!r} is {license_record.status.value}; "
            "production requires an explicitly commercially allowed provider"
        )


def validate_provider_registry(providers: Iterable[LicensedProvider], *, production: bool) -> None:
    seen: set[str] = set()
    for provider in providers:
        if provider.provider_id in seen:
            raise ValueError(f"duplicate provider id: {provider.provider_id}")
        seen.add(provider.provider_id)
        require_production_safe(provider, production=production)
