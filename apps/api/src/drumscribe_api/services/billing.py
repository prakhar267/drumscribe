from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..enums import TranscriptionCreditSource, UserKind
from ..errors import APIError
from ..models import ProcessingJob, Project, User
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
    elif user.free_transcription_used_at is None:
        user.free_transcription_used_at = utcnow()
        job.credit_source = TranscriptionCreditSource.FREE
    elif user.paid_credit_balance > 0:
        user.paid_credit_balance -= 1
        job.credit_source = TranscriptionCreditSource.PAID
    else:
        raise APIError(
            402,
            "TRANSCRIPTION_CREDIT_REQUIRED",
            "Your free song has been used. Buy transcription credits to process another song.",
            title="Transcription credit required",
        )
    job.credit_refunded_at = None
    await db.flush()


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
        user.free_transcription_used_at = None
    elif job.credit_source == TranscriptionCreditSource.PAID:
        user.paid_credit_balance += 1
    job.credit_refunded_at = utcnow()
    await db.flush()
