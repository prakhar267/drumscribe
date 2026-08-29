import io
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from drumscribe_api.config import Environment, Settings
from drumscribe_api.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment=Environment.TESTING,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        storage_backend="local",
        local_storage_path=tmp_path / "objects",
        queue_backend="none",
        auto_create_schema=True,
        session_secret="test-secret-that-is-long-enough-for-signatures",
        cookie_secure=False,
        dev_expose_magic_link=True,
        enable_rate_limiting=False,
        public_api_url="http://testserver",
        web_origins=["http://testserver"],
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def wav_bytes(duration_seconds: float = 1.0, sample_rate: int = 8_000) -> bytes:
    frames = max(1, round(duration_seconds * sample_rate))
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def create_session(client: TestClient) -> str:
    response = client.post("/api/v1/auth/anonymous-session")
    assert response.status_code in {200, 201}, response.text
    token = client.cookies.get("drumscribe_session")
    assert token
    return token


def create_project(client: TestClient, token: str | None = None, title: str = "Test song") -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post("/api/v1/projects", json={"title": title}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def upload_wav(
    client: TestClient,
    project_id: str,
    data: bytes | None = None,
    token: str | None = None,
) -> dict:
    audio = data or wav_bytes()
    auth = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        f"/api/v1/projects/{project_id}/uploads/presign",
        json={
            "filename": "practice.wav",
            "contentType": "audio/wav",
            "sizeBytes": len(audio),
            "rightToUploadConfirmed": True,
        },
        headers=auth,
    )
    assert response.status_code == 201, response.text
    signed = response.json()
    put_response = client.put(
        signed["uploadUrl"],
        content=audio,
        headers=signed["requiredHeaders"],
    )
    assert put_response.status_code == 204, put_response.text
    completed = client.post(
        f"/api/v1/uploads/{signed['assetId']}/complete",
        json={},
        headers=auth,
    )
    assert completed.status_code == 200, completed.text
    return completed.json()


def process_project(client: TestClient, app: Any, project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers={"Idempotency-Key": f"process-{project_id}"},
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert client.portal is not None
    client.portal.call(app.state.pipeline.run, __import__("uuid").UUID(job["id"]))
    status_response = client.get(f"/api/v1/jobs/{job['id']}")
    assert status_response.status_code == 200, status_response.text
    return status_response.json()

