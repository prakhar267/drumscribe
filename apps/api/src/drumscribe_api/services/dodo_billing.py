from __future__ import annotations

from typing import Any

import httpx
from standardwebhooks.webhooks import Webhook

from ..config import Settings
from ..errors import APIError
from ..models import CreditPurchase


class DodoBillingService:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.client = client

    @property
    def enabled(self) -> bool:
        return self.settings.billing_provider == "dodo"

    @property
    def base_url(self) -> str:
        if self.settings.dodo_payments_environment == "live_mode":
            return "https://live.dodopayments.com"
        return "https://test.dodopayments.com"

    async def create_checkout(self, purchase: CreditPurchase, email: str) -> dict[str, str]:
        if not self.enabled:
            raise APIError(
                503,
                "CHECKOUT_UNAVAILABLE",
                "Secure checkout is being activated. Your free song remains available.",
            )
        api_key = self.settings.dodo_payments_api_key
        product_id = self.settings.dodo_credit_pack_product_id
        return_url = self.settings.billing_return_url
        cancel_url = self.settings.billing_cancel_url
        if api_key is None or product_id is None or return_url is None or cancel_url is None:
            raise APIError(503, "CHECKOUT_UNAVAILABLE", "Secure checkout is not configured.")
        payload: dict[str, Any] = {
            "product_cart": [{"product_id": product_id, "quantity": 1}],
            "customer": {"email": email},
            "return_url": return_url,
            "cancel_url": cancel_url,
            "short_link": True,
            "customization": {"theme": "dark", "show_order_details": True},
            "metadata": {
                "drumscribe_purchase_id": str(purchase.id),
                "drumscribe_user_id": str(purchase.user_id),
                "drumscribe_pack": f"credits_{purchase.credit_count}",
            },
        }
        try:
            response = await self._post(
                f"{self.base_url}/checkouts",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise APIError(
                502,
                "CHECKOUT_PROVIDER_UNAVAILABLE",
                "Secure checkout could not be started. Please try again shortly.",
            ) from exc
        if not isinstance(body, dict):
            raise APIError(502, "CHECKOUT_PROVIDER_INVALID", "Checkout returned invalid data.")
        session_id = body.get("session_id")
        checkout_url = body.get("checkout_url")
        if not isinstance(session_id, str) or not isinstance(checkout_url, str):
            raise APIError(502, "CHECKOUT_PROVIDER_INVALID", "Checkout returned invalid data.")
        if not checkout_url.startswith("https://"):
            raise APIError(502, "CHECKOUT_PROVIDER_INVALID", "Checkout returned an unsafe URL.")
        return {"session_id": session_id, "checkout_url": checkout_url}

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
        if not self.enabled or self.settings.dodo_payments_webhook_key is None:
            raise APIError(503, "WEBHOOK_UNAVAILABLE", "Payment webhooks are not configured.")
        try:
            verified = Webhook(self.settings.dodo_payments_webhook_key.get_secret_value()).verify(
                raw_body, headers
            )
        except Exception as exc:
            raise APIError(401, "WEBHOOK_SIGNATURE_INVALID", "Invalid webhook signature.") from exc
        if not isinstance(verified, dict):
            raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Invalid webhook payload.")
        return verified

    async def _post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        if self.client is not None:
            return await self.client.post(url, json=json, headers=headers)
        async with httpx.AsyncClient(timeout=15) as client:
            return await client.post(url, json=json, headers=headers)
