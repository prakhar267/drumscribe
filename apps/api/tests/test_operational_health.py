import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient


def test_liveness_and_readiness_report_healthy_dependencies(client: TestClient) -> None:
    live = client.get("/api/v1/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["status"] == "ready"
    assert set(payload["checks"]) == {"database", "queue", "storage", "provider"}
    assert all(check["status"] == "ok" for check in payload["checks"].values())
    assert all(check["latencyMs"] >= 0 for check in payload["checks"].values())


def test_readiness_returns_503_without_making_liveness_fail(
    client: TestClient,
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable() -> None:
        raise ConnectionError("private storage is offline")

    monkeypatch.setattr(app.state.storage, "healthcheck", unavailable)

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 503
    payload = ready.json()
    assert payload["status"] == "unready"
    assert payload["checks"]["storage"]["status"] == "unavailable"
    assert payload["checks"]["database"]["status"] == "ok"
    assert "offline" not in ready.text
    assert client.get("/api/v1/health/live").status_code == 200


def test_readiness_bounds_each_dependency_check(
    client: TestClient,
    app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def stalled() -> None:
        await asyncio.sleep(60)

    monkeypatch.setattr(app.state.settings, "readiness_timeout_seconds", 0.01)
    monkeypatch.setattr(app.state.queue, "healthcheck", stalled)

    ready = client.get("/api/v1/health/ready")
    assert ready.status_code == 503
    assert ready.json()["checks"]["queue"]["status"] == "unavailable"
