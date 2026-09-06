from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from drumscribe_api.models import User

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
