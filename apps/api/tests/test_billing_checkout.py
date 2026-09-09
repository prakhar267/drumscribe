import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from standardwebhooks.webhooks import Webhook

from drumscribe_api.config import Environment, Settings
from drumscribe_api.errors import APIError
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

    refund_event = {
        "type": "refund.succeeded",
        "data": {
            "payment_id": "pay_1",
            "refund_id": "refund_1",
            "is_partial": False,
            "status": "succeeded",
        },
    }
    monkeypatch.setattr(app.state.billing, "verify_webhook", lambda body, headers: refund_event)
    refunded = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(refund_event),
        headers={
            "Content-Type": "application/json",
            "webhook-id": "webhook_refund_1",
            "webhook-signature": "verified-by-test-double",
            "webhook-timestamp": "0",
        },
    )
    assert refunded.status_code == 200, refunded.text
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 0

    replayed_refund = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(refund_event),
        headers={
            "Content-Type": "application/json",
            "webhook-id": "webhook_refund_replay",
            "webhook-signature": "verified-by-test-double",
            "webhook-timestamp": "0",
        },
    )
    assert replayed_refund.status_code == 200
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 0

    # A delayed replay of the original success event cannot resurrect a refunded pack.
    monkeypatch.setattr(app.state.billing, "verify_webhook", lambda body, headers: event)
    stale_success = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(event),
        headers={
            "Content-Type": "application/json",
            "webhook-id": "webhook_stale_success",
            "webhook-signature": "verified-by-test-double",
            "webhook-timestamp": "0",
        },
    )
    assert stale_success.status_code == 200
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 0

    completed_checkout = client.post(
        "/api/v1/billing/checkout",
        headers={"Idempotency-Key": "pack-attempt-1"},
    )
    assert completed_checkout.status_code == 409
    assert completed_checkout.json()["code"] == "PURCHASE_ALREADY_COMPLETED"


def test_partial_refund_fails_closed_for_manual_reconciliation(
    client: TestClient,
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_session(client)
    account = register_account(client, "partial-refund@example.com")
    captured: dict[str, str] = {}

    async def create_checkout(purchase: CreditPurchase, email: str) -> dict[str, str]:
        captured["purchase_id"] = str(purchase.id)
        return {
            "session_id": "ck_partial_1",
            "checkout_url": "https://checkout.dodopayments.com/session/partial",
        }

    monkeypatch.setattr(app.state.billing, "create_checkout", create_checkout)
    app.state.settings.dodo_credit_pack_product_id = "pdt_credits_10"
    assert (
        client.post(
            "/api/v1/billing/checkout", headers={"Idempotency-Key": "partial-attempt"}
        ).status_code
        == 201
    )
    paid_event = {
        "type": "payment.succeeded",
        "data": {
            "payment_id": "pay_partial_1",
            "checkout_session_id": "ck_partial_1",
            "metadata": {
                "drumscribe_purchase_id": captured["purchase_id"],
                "drumscribe_user_id": account["id"],
                "drumscribe_pack": "credits_10",
            },
            "product_cart": [{"product_id": "pdt_credits_10", "quantity": 1}],
        },
    }
    monkeypatch.setattr(app.state.billing, "verify_webhook", lambda body, headers: paid_event)
    assert (
        client.post(
            "/api/v1/billing/webhooks/dodo",
            content=json.dumps(paid_event),
            headers={"webhook-id": "partial_payment", "webhook-signature": "test"},
        ).status_code
        == 200
    )

    partial_event = {
        "type": "refund.succeeded",
        "data": {
            "payment_id": "pay_partial_1",
            "refund_id": "refund_partial_1",
            "is_partial": True,
        },
    }
    monkeypatch.setattr(app.state.billing, "verify_webhook", lambda body, headers: partial_event)
    response = client.post(
        "/api/v1/billing/webhooks/dodo",
        content=json.dumps(partial_event),
        headers={"webhook-id": "partial_refund", "webhook-signature": "test"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PARTIAL_REFUND_REQUIRES_REVIEW"
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 10


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


def test_dodo_adapter_verifies_standard_webhook_signature() -> None:
    secret = "whsec_dGVzdC1kb2RvLXdlYmhvb2stc2VjcmV0"
    settings = Settings(
        _env_file=None,
        environment=Environment.TESTING,
        billing_provider="dodo",
        dodo_payments_api_key=SecretStr("dodo-test-key"),
        dodo_payments_webhook_key=SecretStr(secret),
        dodo_credit_pack_product_id="pdt_credits_10",
        billing_return_url="http://testserver/billing/success",
        billing_cancel_url="http://testserver/pricing",
    )
    body = json.dumps({"type": "payment.succeeded", "data": {"payment_id": "pay_1"}})
    timestamp = datetime.now(UTC)
    signature = Webhook(secret).sign("webhook_signed_1", timestamp, body)
    verified = DodoBillingService(settings).verify_webhook(
        body.encode(),
        {
            "webhook-id": "webhook_signed_1",
            "webhook-signature": signature,
            "webhook-timestamp": str(int(timestamp.timestamp())),
        },
    )
    assert verified["type"] == "payment.succeeded"

    with pytest.raises(APIError) as error:
        DodoBillingService(settings).verify_webhook(
            body.replace("pay_1", "pay_tampered").encode(),
            {
                "webhook-id": "webhook_signed_1",
                "webhook-signature": signature,
                "webhook-timestamp": str(int(timestamp.timestamp())),
            },
        )
    assert error.value.code == "WEBHOOK_SIGNATURE_INVALID"
