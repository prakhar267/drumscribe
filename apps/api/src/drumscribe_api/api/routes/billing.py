import uuid

from fastapi import APIRouter, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import require_registered
from ...dependencies import CurrentPrincipal, DBSession
from ...enums import CreditPurchaseStatus
from ...errors import APIError
from ...models import CreditPurchase
from ...schemas import BillingWebhookResponse, CheckoutSessionResponse
from ...security import utcnow
from ...services.audit import record_audit, record_product_event
from ...services.billing import lock_user

router = APIRouter(prefix="/billing", tags=["billing"])


def _idempotency_key(value: str | None) -> str:
    clean = value.strip() if value else ""
    if not clean:
        raise APIError(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide an Idempotency-Key header for this operation.",
        )
    if len(clean) > 128:
        raise APIError(400, "IDEMPOTENCY_KEY_INVALID", "Idempotency-Key is too long.")
    return clean


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    request: Request,
    db: DBSession,
    principal: CurrentPrincipal,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CheckoutSessionResponse:
    await require_registered(principal)
    if principal.user.email is None:
        raise APIError(403, "ACCOUNT_REQUIRED", "A verified email account is required.")
    clean_key = _idempotency_key(idempotency_key)
    user = await lock_user(db, principal.user.id)
    if user.email is None:
        raise APIError(403, "ACCOUNT_REQUIRED", "A verified email account is required.")
    existing = (
        await db.execute(
            select(CreditPurchase).where(
                CreditPurchase.user_id == user.id,
                CreditPurchase.idempotency_key == clean_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.status != CreditPurchaseStatus.PENDING:
        raise APIError(
            409,
            "PURCHASE_ALREADY_COMPLETED",
            "This checkout attempt is closed. Start a new checkout to buy another pack.",
        )
    if existing is not None and existing.checkout_url:
        return CheckoutSessionResponse(checkout_url=existing.checkout_url)
    if existing is not None:
        purchase = existing
    else:
        purchase = CreditPurchase(
            user_id=user.id,
            provider="dodo",
            idempotency_key=clean_key,
            status=CreditPurchaseStatus.PENDING,
            credit_count=request.app.state.settings.credit_pack_size,
        )
        db.add(purchase)
        await db.flush()
    checkout = await request.app.state.billing.create_checkout(purchase, user.email)
    purchase.checkout_session_id = checkout["session_id"]
    purchase.checkout_url = checkout["checkout_url"]
    record_audit(
        db,
        "billing.checkout_created",
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"purchaseId": str(purchase.id), "creditCount": purchase.credit_count},
    )
    await db.commit()
    return CheckoutSessionResponse(checkout_url=purchase.checkout_url)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if isinstance(item, str)}


@router.post("/webhooks/dodo", response_model=BillingWebhookResponse)
async def dodo_webhook(
    request: Request,
    db: DBSession,
) -> BillingWebhookResponse:
    raw_body = await request.body()
    webhook_id = request.headers.get("webhook-id", "")
    verified = request.app.state.billing.verify_webhook(
        raw_body,
        {
            "webhook-id": webhook_id,
            "webhook-signature": request.headers.get("webhook-signature", ""),
            "webhook-timestamp": request.headers.get("webhook-timestamp", ""),
        },
    )
    if not webhook_id:
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Webhook identifier is missing.")
    event_type = verified.get("type")
    if event_type not in {"payment.succeeded", "refund.succeeded"}:
        return BillingWebhookResponse()
    data = verified.get("data")
    if not isinstance(data, dict):
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Payment event data is missing.")
    if event_type == "refund.succeeded":
        await _apply_successful_refund(request, db, data, webhook_id)
        return BillingWebhookResponse()

    metadata = _string_mapping(data.get("metadata"))
    purchase_id = metadata.get("drumscribe_purchase_id")
    user_id = metadata.get("drumscribe_user_id")
    try:
        parsed_purchase_id = uuid.UUID(purchase_id or "")
    except ValueError:
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Purchase metadata is missing.") from None
    purchase_snapshot = await db.get(CreditPurchase, parsed_purchase_id)
    if purchase_snapshot is None:
        raise APIError(404, "PURCHASE_NOT_FOUND", "The referenced purchase was not found.")
    if str(purchase_snapshot.user_id) != user_id:
        raise APIError(400, "WEBHOOK_PURCHASE_MISMATCH", "Purchase metadata did not match.")
    user = await lock_user(db, purchase_snapshot.user_id)
    purchase = (
        await db.execute(
            select(CreditPurchase).where(CreditPurchase.id == parsed_purchase_id).with_for_update()
        )
    ).scalar_one()
    if purchase.status in {CreditPurchaseStatus.PAID, CreditPurchaseStatus.REFUNDED}:
        return BillingWebhookResponse()
    checkout_session_id = data.get("checkout_session_id")
    if purchase.checkout_session_id and checkout_session_id != purchase.checkout_session_id:
        raise APIError(400, "WEBHOOK_PURCHASE_MISMATCH", "Checkout session did not match.")
    configured_product_id = request.app.state.settings.dodo_credit_pack_product_id
    product_cart = data.get("product_cart")
    valid_cart = (
        isinstance(product_cart, list)
        and len(product_cart) == 1
        and isinstance(product_cart[0], dict)
        and product_cart[0].get("product_id") == configured_product_id
        and product_cart[0].get("quantity") == 1
    )
    if not valid_cart:
        raise APIError(400, "WEBHOOK_PRODUCT_MISMATCH", "Payment product did not match.")
    if metadata.get("drumscribe_pack") != f"credits_{purchase.credit_count}":
        raise APIError(400, "WEBHOOK_PRODUCT_MISMATCH", "Payment pack did not match.")
    payment_id = data.get("payment_id")
    if not isinstance(payment_id, str) or not payment_id:
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Payment identifiers are missing.")
    payment_owner = (
        await db.execute(
            select(CreditPurchase).where(CreditPurchase.provider_payment_id == payment_id)
        )
    ).scalar_one_or_none()
    if payment_owner is not None and payment_owner.id != purchase.id:
        raise APIError(409, "WEBHOOK_PAYMENT_REUSED", "Payment was already applied.")

    user.paid_credit_balance += purchase.credit_count
    purchase.remaining_credit_count = purchase.credit_count
    purchase.status = CreditPurchaseStatus.PAID
    purchase.provider_payment_id = payment_id
    purchase.last_webhook_id = webhook_id
    purchase.paid_at = utcnow()
    purchase.checkout_url = None
    record_audit(
        db,
        "billing.credits_granted",
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={"purchaseId": str(purchase.id), "creditCount": purchase.credit_count},
    )
    record_product_event(
        db,
        "credit_pack_purchased",
        user_id=user.id,
        properties={"creditCount": purchase.credit_count},
    )
    await db.commit()
    return BillingWebhookResponse()


async def _apply_successful_refund(
    request: Request,
    db: AsyncSession,
    data: dict[object, object],
    webhook_id: str,
) -> None:
    payment_id = data.get("payment_id")
    refund_id = data.get("refund_id")
    is_partial = data.get("is_partial")
    if (
        not isinstance(payment_id, str)
        or not payment_id
        or not isinstance(refund_id, str)
        or not refund_id
        or not isinstance(is_partial, bool)
    ):
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Refund identifiers are missing.")
    if is_partial:
        # A partial cash refund cannot be translated safely into indivisible song
        # credits without an explicit operator decision.
        raise APIError(
            409,
            "PARTIAL_REFUND_REQUIRES_REVIEW",
            "Partial refunds require a manual credit adjustment.",
        )
    purchase_snapshot = (
        await db.execute(
            select(CreditPurchase).where(CreditPurchase.provider_payment_id == payment_id)
        )
    ).scalar_one_or_none()
    if purchase_snapshot is None:
        raise APIError(404, "PURCHASE_NOT_FOUND", "The refunded purchase was not found.")
    user = await lock_user(db, purchase_snapshot.user_id)
    purchase = (
        await db.execute(
            select(CreditPurchase)
            .where(CreditPurchase.id == purchase_snapshot.id)
            .with_for_update()
        )
    ).scalar_one()
    if purchase.status == CreditPurchaseStatus.REFUNDED:
        return
    if purchase.status != CreditPurchaseStatus.PAID:
        raise APIError(409, "PURCHASE_NOT_PAID", "The refunded purchase is not paid.")

    credits_to_revoke = purchase.remaining_credit_count
    if user.paid_credit_balance < credits_to_revoke:
        raise APIError(
            409,
            "CREDIT_BALANCE_INCONSISTENT",
            "The refund requires a manual credit reconciliation.",
        )
    user.paid_credit_balance -= credits_to_revoke
    purchase.remaining_credit_count = 0
    purchase.revoked_credit_count = credits_to_revoke
    purchase.status = CreditPurchaseStatus.REFUNDED
    purchase.provider_refund_id = refund_id
    purchase.last_webhook_id = webhook_id
    purchase.refunded_at = utcnow()
    purchase.checkout_url = None
    record_audit(
        db,
        "billing.credits_revoked",
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        metadata={
            "purchaseId": str(purchase.id),
            "creditCount": credits_to_revoke,
            "reason": "full_refund",
        },
    )
    record_product_event(
        db,
        "credit_pack_refunded",
        user_id=user.id,
        properties={"creditCount": credits_to_revoke},
    )
    await db.commit()
