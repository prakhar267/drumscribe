from fastapi.testclient import TestClient

from drumscribe_api.services.magic_links import MagicLinkDelivery

from .conftest import create_project, create_session


def test_health_and_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]


def test_magic_link_delivery_targets_the_web_verification_route(settings) -> None:
    link = MagicLinkDelivery(settings).verification_url("opaque+/token")
    assert link == "http://testserver/auth/verify?token=opaque%2B%2Ftoken"


def test_user_a_cannot_read_or_mutate_user_b_project(client: TestClient) -> None:
    token_a = create_session(client)
    project_a = create_project(client, token_a, "A private chart")

    client.cookies.clear()
    token_b = create_session(client)
    for method, path, kwargs in [
        ("get", f"/api/v1/projects/{project_a['id']}", {}),
        ("patch", f"/api/v1/projects/{project_a['id']}", {"json": {"title": "stolen"}}),
        ("delete", f"/api/v1/projects/{project_a['id']}", {}),
    ]:
        response = getattr(client, method)(
            path,
            headers={"Authorization": f"Bearer {token_b}"},
            **kwargs,
        )
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    response = client.get(
        f"/api/v1/projects/{project_a['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 200


def test_magic_link_transfers_anonymous_projects(client: TestClient) -> None:
    create_session(client)
    project = create_project(client, title="Keep me through signup")
    request = client.post("/api/v1/auth/magic-link/request", json={"email": "Drummer@Example.com"})
    assert request.status_code == 202
    assert request.json()["accepted"] is True
    token = request.json()["devToken"]

    consume = client.post("/api/v1/auth/magic-link/consume", json={"token": token})
    assert consume.status_code == 200
    assert consume.json()["user"]["email"] == "drummer@example.com"
    assert consume.json()["user"]["kind"] == "REGISTERED"
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200

    replay = client.post("/api/v1/auth/magic-link/consume", json={"token": token})
    assert replay.status_code == 400
    assert replay.json()["code"] == "MAGIC_LINK_INVALID"


def test_project_search_sort_soft_delete_and_restore(client: TestClient) -> None:
    create_session(client)
    first = create_project(client, title="Neon Moon")
    create_project(client, title="Amber Sky")
    listing = client.get("/api/v1/projects?q=moon&sort=name")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["id"] == first["id"]

    deleted = client.delete(f"/api/v1/projects/{first['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/projects/{first['id']}").status_code == 404
    restored = client.post(f"/api/v1/projects/{first['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["id"] == first["id"]


def test_deleted_account_can_register_the_same_email_again(client: TestClient) -> None:
    create_session(client)
    first_link = client.post(
        "/api/v1/auth/magic-link/request", json={"email": "returning@example.com"}
    ).json()["devToken"]
    assert (
        client.post("/api/v1/auth/magic-link/consume", json={"token": first_link}).status_code
        == 200
    )

    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        json={"confirmation": "DELETE MY ACCOUNT"},
    )
    assert deleted.status_code == 200, deleted.text

    second_link = client.post(
        "/api/v1/auth/magic-link/request", json={"email": "returning@example.com"}
    ).json()["devToken"]
    registered = client.post("/api/v1/auth/magic-link/consume", json={"token": second_link})
    assert registered.status_code == 200, registered.text
    assert registered.json()["user"]["email"] == "returning@example.com"
