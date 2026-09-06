import uuid

from fastapi import APIRouter, Header, Request, status
from sqlalchemy import select

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
    existing = (
        await db.execute(
            select(CreditPurchase).where(
                CreditPurchase.user_id == principal.user.id,
                CreditPurchase.idempotency_key == clean_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None and existing.status == CreditPurchaseStatus.PAID:
        raise APIError(
            409,
            "PURCHASE_ALREADY_COMPLETED",
            "This checkout attempt already completed. Start a new checkout to buy another pack.",
        )
    if existing is not None and existing.checkout_url:
        return CheckoutSessionResponse(checkout_url=existing.checkout_url)
    if existing is not None:
        purchase = existing
    else:
        purchase = CreditPurchase(
            user_id=principal.user.id,
            provider="dodo",
            idempotency_key=clean_key,
            status=CreditPurchaseStatus.PENDING,
            credit_count=request.app.state.settings.credit_pack_size,
        )
        db.add(purchase)
        await db.flush()
    checkout = await request.app.state.billing.create_checkout(purchase, principal.user.email)
    purchase.checkout_session_id = checkout["session_id"]
    purchase.checkout_url = checkout["checkout_url"]
    record_audit(
        db,
        "billing.checkout_created",
        user_id=principal.user.id,
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
    if verified.get("type") != "payment.succeeded":
        return BillingWebhookResponse()
    data = verified.get("data")
    if not isinstance(data, dict):
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Payment data is missing.")
    metadata = _string_mapping(data.get("metadata"))
    purchase_id = metadata.get("drumscribe_purchase_id")
    user_id = metadata.get("drumscribe_user_id")
    try:
        parsed_purchase_id = uuid.UUID(purchase_id or "")
    except ValueError:
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Purchase metadata is missing.") from None
    purchase = (
        await db.execute(
            select(CreditPurchase)
            .where(CreditPurchase.id == parsed_purchase_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if purchase is None:
        raise APIError(404, "PURCHASE_NOT_FOUND", "The referenced purchase was not found.")
    if purchase.status == CreditPurchaseStatus.PAID:
        return BillingWebhookResponse()
    if str(purchase.user_id) != user_id:
        raise APIError(400, "WEBHOOK_PURCHASE_MISMATCH", "Purchase metadata did not match.")
    checkout_session_id = data.get("checkout_session_id")
    if purchase.checkout_session_id and checkout_session_id != purchase.checkout_session_id:
        raise APIError(400, "WEBHOOK_PURCHASE_MISMATCH", "Checkout session did not match.")
    configured_product_id = request.app.state.settings.dodo_credit_pack_product_id
    product_cart = data.get("product_cart")
    purchased_product_ids = (
        {
            item.get("product_id")
            for item in product_cart
            if isinstance(item, dict) and isinstance(item.get("product_id"), str)
        }
        if isinstance(product_cart, list)
        else set()
    )
    if configured_product_id not in purchased_product_ids:
        raise APIError(400, "WEBHOOK_PRODUCT_MISMATCH", "Payment product did not match.")
    payment_id = data.get("payment_id")
    if not isinstance(payment_id, str) or not webhook_id:
        raise APIError(400, "WEBHOOK_PAYLOAD_INVALID", "Payment identifiers are missing.")

    user = await lock_user(db, purchase.user_id)
    user.paid_credit_balance += purchase.credit_count
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
