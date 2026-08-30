from html import escape
from urllib.parse import urlencode

import httpx

from ..config import Settings


class MagicLinkDelivery:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client

    def verification_url(self, token: str) -> str:
        query = urlencode({"token": token})
        return f"{self.settings.web_origins[0].rstrip('/')}/auth/verify?{query}"

    async def deliver(self, email: str, token: str) -> None:
        if self.settings.magic_link_delivery == "development":
            # The token is returned by the development-only API response. Never log it.
            return
        link = self.verification_url(token)
        if self.settings.magic_link_delivery == "resend":
            assert self.settings.resend_api_key is not None
            assert self.settings.resend_from_email is not None
            response = await self._post(
                f"{self.settings.resend_api_url.rstrip('/')}/emails",
                json={
                    "from": self.settings.resend_from_email,
                    "to": [email],
                    "subject": "Sign in to DrumScribe",
                    "text": (
                        "Use this private link to sign in to DrumScribe. "
                        f"It expires in 15 minutes:\n\n{link}\n\n"
                        "If you did not request this email, you can ignore it."
                    ),
                    "html": (
                        "<p>Use this private link to sign in to DrumScribe. "
                        "It expires in 15 minutes.</p>"
                        f'<p><a href="{escape(link, quote=True)}">Sign in to DrumScribe</a></p>'
                        "<p>If you did not request this email, you can ignore it.</p>"
                    ),
                },
                headers={
                    "Authorization": ("Bearer " + self.settings.resend_api_key.get_secret_value())
                },
            )
            response.raise_for_status()
            return

        assert self.settings.magic_link_webhook_url is not None
        headers: dict[str, str] = {}
        if self.settings.magic_link_webhook_secret:
            headers["Authorization"] = (
                "Bearer " + self.settings.magic_link_webhook_secret.get_secret_value()
            )
        response = await self._post(
            self.settings.magic_link_webhook_url,
            json={"template": "magic-link", "recipient": email, "link": link},
            headers=headers,
        )
        response.raise_for_status()

    async def _post(
        self,
        url: str,
        *,
        json: dict[str, object],
        headers: dict[str, str],
    ) -> httpx.Response:
        if self.client is not None:
            return await self.client.post(url, json=json, headers=headers)
        async with httpx.AsyncClient(timeout=10) as client:
            return await client.post(url, json=json, headers=headers)
