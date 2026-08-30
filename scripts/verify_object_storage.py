"""Opt-in live verification for the configured private S3-compatible bucket."""

from __future__ import annotations

import asyncio
import uuid

import httpx
from drumscribe_api.config import Settings
from drumscribe_api.services.storage import S3PrivateStorage


async def verify() -> None:
    settings = Settings()
    if settings.storage_backend != "s3":
        raise RuntimeError("DRUMSCRIBE_STORAGE_BACKEND must be s3")

    storage = S3PrivateStorage(settings)
    prefix = f"setup-check/{uuid.uuid4()}"
    server_key = f"{prefix}/server.txt"
    browser_key = f"{prefix}/browser.txt"
    copied_key = f"{prefix}/copied.txt"
    payload = b"drumscribe-private-storage"
    keys = [server_key, browser_key, copied_key]

    unsigned_status = 0
    try:
        await storage.healthcheck()
        await storage.configure_browser_cors(settings.web_origins)
        await storage.put_bytes(server_key, payload, "text/plain")
        metadata = await storage.head(server_key)
        assert metadata.size_bytes == len(payload)
        assert await storage.read_prefix(server_key) == payload

        signed_put = await storage.presign_put(browser_key, "text/plain", len(payload), 60)
        signed_get = await storage.presign_get(server_key, 60)
        async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
            put_response = await client.put(
                signed_put.url,
                content=payload,
                headers=signed_put.required_headers,
            )
            assert put_response.status_code in {200, 201, 204}, put_response.text
            get_response = await client.get(signed_get.url)
            assert get_response.status_code == 200
            assert get_response.content == payload
            unsigned_response = await client.get(
                f"{settings.s3_public_endpoint_url}/{settings.s3_bucket}/{server_key}"
            )
            unsigned_status = unsigned_response.status_code
            assert unsigned_status in {401, 403, 404}

        await storage.copy(server_key, copied_key, "text/plain")
        assert await storage.read_prefix(copied_key) == payload
    finally:
        await storage.delete_many(keys)

    print(
        "storage_health=ok presigned_put=ok presigned_get=ok "
        f"unsigned_get={unsigned_status} copy=ok cleanup=ok"
    )


if __name__ == "__main__":
    asyncio.run(verify())
