"""Configuration contract for a future commercially licensed provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class CommercialProviderConfig:
    provider_id: str
    endpoint: str
    api_key: str
    contract_reference: str
    commercial_license_confirmed: bool = False

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("commercial provider endpoint must use HTTPS")
        if not self.api_key:
            raise ValueError("api_key is required")
        if not self.contract_reference.strip():
            raise ValueError("contract_reference is required for auditability")
        if not self.commercial_license_confirmed:
            raise ValueError("commercial provider cannot be enabled before license confirmation")
