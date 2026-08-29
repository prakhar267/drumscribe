from urllib.parse import urlencode

import httpx

from ..config import Settings


class MagicLinkDelivery:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verification_url(self, token: str) -> str:
        query = urlencode({"token": token})
        return f"{self.settings.web_origins[0].rstrip('/')}/auth/verify?{query}"

    async def deliver(self, email: str, token: str) -> None:
        if self.settings.magic_link_delivery == "development":
            # The token is returned by the development-only API response. Never log it.
            return
        assert self.settings.magic_link_webhook_url is not None
        link = self.verification_url(token)
        headers: dict[str, str] = {}
        if self.settings.magic_link_webhook_secret:
            headers["Authorization"] = (
                "Bearer " + self.settings.magic_link_webhook_secret.get_secret_value()
            )
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.settings.magic_link_webhook_url,
                json={"template": "magic-link", "recipient": email, "link": link},
                headers=headers,
            )
            response.raise_for_status()
