import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from drumscribe_api.config import Environment, Settings
from drumscribe_api.models import CreditPurchase
from drumscribe_api.services.dodo_billing import DodoBillingService

from .conftest import create_session
from .test_transcription_credits import register_account


def test_checkout_requires_a_verified_account(client: TestClient) -> None:
    create_session(client)
    response = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "anonymous-checkout"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_REQUIRED"


def test_checkout_and_payment_webhook_grant_ten_credits_once(
    client: TestClient,
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_session(client)
    account = register_account(client, "buyer@example.com")
    captured: dict[str, str] = {}

    async def create_checkout(purchase: CreditPurchase, email: str) -> dict[str, str]:
        captured["purchase_id"] = str(purchase.id)
        captured["user_id"] = str(purchase.user_id)
        captured["email"] = email
        return {
            "session_id": "ck_session_1",
            "checkout_url": "https://checkout.dodopayments.com/session/1",
        }

    monkeypatch.setattr(app.state.billing, "create_checkout", create_checkout)
    app.state.settings.dodo_credit_pack_product_id = "pdt_credits_10"
    created = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "pack-attempt-1"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["checkoutUrl"].startswith("https://checkout.dodopayments.com/")
    assert captured["email"] == "buyer@example.com"

    repeated = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "pack-attempt-1"},
    )
    assert repeated.status_code == 201
    assert repeated.json() == created.json()

    event = {
        "type": "payment.succeeded",
        "data": {
            "payment_id": "pay_1",
            "checkout_session_id": "ck_session_1",
            "metadata": {
                "drumscribe_purchase_id": captured["purchase_id"],
                "drumscribe_user_id": account["id"],
                "drumscribe_pack": "credits_10",
            },
            "product_cart": [{"product_id": "pdt_credits_10", "quantity": 1}],
        },
    }
    monkeypatch.setattr(app.state.billing, "verify_webhook", lambda body, headers: event)
    paid = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(event),
        headers={
            "Content-Type": "application/json",
            "webhook-id": "webhook_1",
            "webhook-signature": "verified-by-test-double",
            "webhook-timestamp": "0",
        },
    )
    assert paid.status_code == 200, paid.text
    assert paid.json() == {"received": True}
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 10

    duplicate = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(event),
        headers={
            "Content-Type": "application/json",
            "webhook-id": "webhook_2",
            "webhook-signature": "verified-by-test-double",
            "webhook-timestamp": "0",
        },
    )
    assert duplicate.status_code == 200
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 10

    completed_checkout = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "pack-attempt-1"},
    )
    assert completed_checkout.status_code == 409
    assert completed_checkout.json()["code"] == "PURCHASE_ALREADY_COMPLETED"


@pytest.mark.asyncio
async def test_dodo_adapter_creates_a_server_bound_checkout() -> None:
    captured: dict[str, Any] = {}

    async def send(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "session_id": "ck_test_1",
                "checkout_url": "https://checkout.dodopayments.com/session/test",
            },
        )

    settings = Settings(
        _env_file=None,
        environment=Environment.TESTING,
        billing_provider="dodo",
        dodo_payments_api_key=SecretStr("dodo-test-key"),
        dodo_payments_webhook_key=SecretStr("whsec_dGVzdA=="),
        dodo_credit_pack_product_id="pdt_credits_10",
        billing_return_url="http://testserver/billing/success",
        billing_cancel_url="http://testserver/pricing",
    )
    purchase = CreditPurchase(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        idempotency_key="attempt-1",
        credit_count=10,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http_client:
        checkout = await DodoBillingService(settings, http_client).create_checkout(
            purchase,
            "buyer@example.com",
        )

    assert checkout["session_id"] == "ck_test_1"
    assert captured["url"] == "https://test.dodopayments.com/checkouts"
    assert captured["authorization"] == "Bearer dodo-test-key"
    payload = captured["payload"]
    assert payload["product_cart"] == [{"product_id": "pdt_credits_10", "quantity": 1}]
    assert payload["customer"] == {"email": "buyer@example.com"}
    assert payload["return_url"] == "http://testserver/billing/success"
    assert payload["cancel_url"] == "http://testserver/pricing"
    assert payload["metadata"]["drumscribe_purchase_id"] == str(purchase.id)
    assert payload["metadata"]["drumscribe_user_id"] == str(purchase.user_id)
