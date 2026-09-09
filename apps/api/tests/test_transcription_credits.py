import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from drumscribe_api.auth import backfill_free_transcription_claims
from drumscribe_api.enums import CreditPurchaseStatus, UserKind
from drumscribe_api.models import CreditPurchase, FreeTranscriptionClaim, ProcessingJob, User
from drumscribe_api.security import utcnow

from .conftest import create_project, create_session, process_project, upload_wav


def register_account(client: TestClient, email: str = "drummer@example.com") -> dict[str, Any]:
    request = client.post("/api/v1/auth/magic-link/request", json={"email": email})
    assert request.status_code == 202, request.text
    response = client.post(
        "/api/v1/auth/magic-link/consume",
        json={"token": request.json()["devToken"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


async def grant_paid_credits(app: Any, email: str, amount: int) -> None:
    async with app.state.database.session_factory() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.paid_credit_balance += amount
        await db.commit()


def test_registered_account_gets_one_free_song_then_needs_credits(
    client: TestClient,
    app: Any,
) -> None:
    create_session(client)
    account = register_account(client)
    assert account["freeTranscriptionsRemaining"] == 1
    assert account["paidCredits"] == 0
    assert account["canStartFullTranscription"] is True

    free_project = create_project(client, title="Free song")
    upload_wav(client, free_project["id"])
    job = process_project(client, app, free_project["id"])
    assert job["stage"] == "READY"

    used_account = client.get("/api/v1/account/me").json()
    assert used_account["freeTranscriptionsRemaining"] == 0
    assert used_account["canStartFullTranscription"] is False

    paid_project = create_project(client, title="Second song")
    upload_wav(client, paid_project["id"])
    blocked = client.post(
        f"/api/v1/projects/{paid_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "second-song"},
    )
    assert blocked.status_code == 402, blocked.text
    assert blocked.json()["code"] == "TRANSCRIPTION_CREDIT_REQUIRED"

    assert client.portal is not None
    client.portal.call(grant_paid_credits, app, "drummer@example.com", 2)
    started = client.post(
        f"/api/v1/projects/{paid_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "second-song"},
    )
    assert started.status_code == 202, started.text
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 1

    repeated = client.post(
        f"/api/v1/projects/{paid_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "second-song"},
    )
    assert repeated.status_code == 202, repeated.text
    assert repeated.json()["id"] == started.json()["id"]
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 1


def test_cancelled_job_returns_reserved_free_song(client: TestClient) -> None:
    create_session(client)
    register_account(client, "cancel@example.com")
    project = create_project(client)
    upload_wav(client, project["id"])
    started = client.post(
        f"/api/v1/projects/{project['id']}/process",
        json={},
        headers={"Idempotency-Key": "cancel-free"},
    )
    assert started.status_code == 202, started.text
    assert client.get("/api/v1/account/me").json()["freeTranscriptionsRemaining"] == 0

    cancelled = client.post(f"/api/v1/jobs/{started.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["stage"] == "CANCELLED"
    account = client.get("/api/v1/account/me").json()
    assert account["freeTranscriptionsRemaining"] == 1
    assert account["canStartFullTranscription"] is True


def test_anonymous_preview_does_not_consume_registered_free_song(
    client: TestClient,
    app: Any,
) -> None:
    create_session(client)
    preview = create_project(client, title="Anonymous preview")
    upload_wav(client, preview["id"])
    job = process_project(client, app, preview["id"])
    assert job["stage"] == "READY"

    anonymous = client.get("/api/v1/account/me").json()
    assert anonymous["freeTranscriptionsRemaining"] == 0
    assert anonymous["canStartFullTranscription"] is False

    registered = register_account(client, "preview@example.com")
    assert registered["freeTranscriptionsRemaining"] == 1
    assert registered["canStartFullTranscription"] is True


def test_used_free_song_survives_account_deletion_and_gmail_alias_signup(
    client: TestClient,
    app: Any,
) -> None:
    create_session(client)
    register_account(client, "Drum.Mer+first@gmail.com")
    project = create_project(client, title="Only free song")
    upload_wav(client, project["id"])
    assert process_project(client, app, project["id"])["stage"] == "READY"

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": "DELETE MY ACCOUNT"},
    )
    assert deleted.status_code == 200, deleted.text

    returning = register_account(client, "drummer@googlemail.com")
    assert returning["freeTranscriptionsRemaining"] == 0
    assert returning["canStartFullTranscription"] is False


def test_paid_job_reservation_and_cancellation_restore_its_purchase_batch(
    client: TestClient,
    app: Any,
) -> None:
    create_session(client)
    register_account(client, "batch@example.com")
    free_project = create_project(client, title="Free song")
    upload_wav(client, free_project["id"])
    assert process_project(client, app, free_project["id"])["stage"] == "READY"

    async def seed_purchase() -> uuid.UUID:
        async with app.state.database.session_factory() as db:
            user = (
                await db.execute(select(User).where(User.email == "batch@example.com"))
            ).scalar_one()
            purchase = CreditPurchase(
                user_id=user.id,
                idempotency_key="seeded-pack",
                status=CreditPurchaseStatus.PAID,
                credit_count=10,
                remaining_credit_count=10,
                paid_at=utcnow(),
            )
            db.add(purchase)
            user.paid_credit_balance = 10
            await db.commit()
            return purchase.id

    assert client.portal is not None
    purchase_id = client.portal.call(seed_purchase)
    paid_project = create_project(client, title="Paid song")
    upload_wav(client, paid_project["id"])
    started = client.post(
        f"/api/v1/projects/{paid_project['id']}/process",
        json={},
        headers={"Idempotency-Key": "paid-song"},
    )
    assert started.status_code == 202, started.text
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 9

    async def purchase_and_job_state() -> tuple[int, uuid.UUID | None]:
        async with app.state.database.session_factory() as db:
            purchase = await db.get(CreditPurchase, purchase_id)
            job = await db.get(ProcessingJob, uuid.UUID(started.json()["id"]))
            assert purchase is not None and job is not None
            return purchase.remaining_credit_count, job.credit_purchase_id

    assert client.portal.call(purchase_and_job_state) == (9, purchase_id)
    cancelled = client.post(f"/api/v1/jobs/{started.json()['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert client.get("/api/v1/account/me").json()["paidCredits"] == 10
    assert client.portal.call(purchase_and_job_state) == (10, purchase_id)


def test_existing_accounts_can_be_backfilled_idempotently(
    client: TestClient,
    app: Any,
    settings: Any,
) -> None:
    used_at = utcnow()

    async def create_legacy_account() -> uuid.UUID:
        async with app.state.database.session_factory() as db:
            user = User(
                email="legacy@example.com",
                kind=UserKind.REGISTERED,
                free_transcription_used_at=used_at,
            )
            db.add(user)
            await db.commit()
            return user.id

    async def backfill_and_read(user_id: uuid.UUID) -> tuple[int, int, bool]:
        async with app.state.database.session_factory() as db:
            first_count = await backfill_free_transcription_claims(db, settings)
        async with app.state.database.session_factory() as db:
            second_count = await backfill_free_transcription_claims(db, settings)
            user = await db.get(User, user_id)
            assert user is not None and user.free_transcription_claim_hash is not None
            claim = await db.get(FreeTranscriptionClaim, user.free_transcription_claim_hash)
            return first_count, second_count, claim is not None and claim.used_at is not None

    assert client.portal is not None
    user_id = client.portal.call(create_legacy_account)
    assert client.portal.call(backfill_and_read, user_id) == (1, 0, True)
