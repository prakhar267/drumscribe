from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import TranscriptionCreditSource, UserKind
from ..errors import APIError
from ..models import CreditPurchase, FreeTranscriptionClaim, ProcessingJob, Project, User
from ..security import utcnow


async def lock_user(db: AsyncSession, user_id: object) -> User:
    """Serialize balance changes for a customer in production Postgres."""
    user = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    return user


async def reserve_processing_credit(
    db: AsyncSession,
    user: User,
    job: ProcessingJob,
) -> None:
    """Reserve one entitlement exactly once for a newly created or retried job."""
    if job.credit_source is not None and job.credit_refunded_at is None:
        return

    if user.kind == UserKind.ANONYMOUS:
        # The existing short anonymous preview remains available. It is not the
        # account's one free full-song transcription.
        job.credit_source = TranscriptionCreditSource.ANONYMOUS_PREVIEW
    elif user.free_transcription_claim_hash is not None:
        claim = (
            await db.execute(
                select(FreeTranscriptionClaim)
                .where(FreeTranscriptionClaim.identity_hash == user.free_transcription_claim_hash)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if claim is None:
            raise APIError(
                409,
                "FREE_TRANSCRIPTION_CLAIM_MISSING",
                "Your account entitlement could not be verified. Sign in again and retry.",
            )
        if claim.used_at is None:
            used_at = utcnow()
            claim.used_at = used_at
            user.free_transcription_used_at = used_at
            job.credit_source = TranscriptionCreditSource.FREE
        else:
            user.free_transcription_used_at = claim.used_at
            await _reserve_paid_credit(db, user, job)
    elif user.free_transcription_used_at is None:
        # Compatibility for registered accounts created before the durable
        # identity-claim migration. Their next sign-in attaches a claim.
        user.free_transcription_used_at = utcnow()
        job.credit_source = TranscriptionCreditSource.FREE
    elif user.paid_credit_balance > 0:
        await _reserve_paid_credit(db, user, job)
    else:
        _raise_credit_required()
    job.credit_refunded_at = None
    await db.flush()


def _raise_credit_required() -> None:
    raise APIError(
        402,
        "TRANSCRIPTION_CREDIT_REQUIRED",
        "Your free song has been used. Buy transcription credits to process another song.",
        title="Transcription credit required",
    )


async def _reserve_paid_credit(
    db: AsyncSession,
    user: User,
    job: ProcessingJob,
) -> None:
    if user.paid_credit_balance <= 0:
        _raise_credit_required()
    purchase = (
        (
            await db.execute(
                select(CreditPurchase)
                .where(
                    CreditPurchase.user_id == user.id,
                    CreditPurchase.status == "PAID",
                    CreditPurchase.remaining_credit_count > 0,
                )
                .order_by(CreditPurchase.paid_at, CreditPurchase.created_at)
                .with_for_update()
            )
        )
        .scalars()
        .first()
    )
    user.paid_credit_balance -= 1
    if purchase is not None:
        purchase.remaining_credit_count -= 1
        job.credit_purchase_id = purchase.id
    job.credit_source = TranscriptionCreditSource.PAID


async def refund_processing_credit(db: AsyncSession, job: ProcessingJob) -> None:
    """Return a reserved credit after a terminal failure or cancellation."""
    if (
        job.credit_source is None
        or job.credit_source == TranscriptionCreditSource.ANONYMOUS_PREVIEW
        or job.credit_refunded_at is not None
    ):
        return
    owner_id = await db.scalar(select(Project.owner_id).where(Project.id == job.project_id))
    if owner_id is None:
        return
    user = await lock_user(db, owner_id)
    if job.credit_source == TranscriptionCreditSource.FREE:
        if user.free_transcription_claim_hash is not None:
            claim = (
                await db.execute(
                    select(FreeTranscriptionClaim)
                    .where(
                        FreeTranscriptionClaim.identity_hash == user.free_transcription_claim_hash
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if claim is not None:
                claim.used_at = None
        user.free_transcription_used_at = None
    elif job.credit_source == TranscriptionCreditSource.PAID:
        purchase = (
            await db.execute(
                select(CreditPurchase)
                .where(CreditPurchase.id == job.credit_purchase_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        # A job that fails after its originating payment was refunded must not
        # recreate an entitlement. Legacy/manual credits have no purchase row.
        if purchase is None or purchase.status == "PAID":
            user.paid_credit_balance += 1
            if purchase is not None:
                purchase.remaining_credit_count += 1
    job.credit_refunded_at = utcnow()
    await db.flush()
