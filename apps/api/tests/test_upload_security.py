import asyncio
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from drumscribe_api.config import Settings
from drumscribe_api.errors import APIError
from drumscribe_api.services.audio import sniff_content_type
from drumscribe_api.services.storage import LocalPrivateStorage, S3PrivateStorage

from .conftest import create_project, create_session, wav_bytes


def test_oversize_upload_rejected_before_presign(client: TestClient, settings) -> None:
    create_session(client)
    project = create_project(client)
    response = client.post(
        f"/api/v1/projects/{project['id']}/uploads/presign",
        json={
            "filename": "too-big.wav",
            "contentType": "audio/wav",
            "sizeBytes": settings.max_upload_bytes + 1,
            "rightToUploadConfirmed": True,
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "AUDIO_TOO_LARGE"


def test_rights_confirmation_and_mime_contract_are_mandatory(client: TestClient) -> None:
    create_session(client)
    project = create_project(client)
    base = {
        "filename": "song.exe",
        "contentType": "application/octet-stream",
        "sizeBytes": 100,
        "rightToUploadConfirmed": True,
    }
    unsupported = client.post(f"/api/v1/projects/{project['id']}/uploads/presign", json=base)
    assert unsupported.status_code == 415
    base["contentType"] = "audio/wav"
    base["rightToUploadConfirmed"] = False
    no_rights = client.post(f"/api/v1/projects/{project['id']}/uploads/presign", json=base)
    assert no_rights.status_code == 422


def _run_failed_validation(client: TestClient, app, project_id: str, key: str) -> dict:
    started = client.post(
        f"/api/v1/projects/{project_id}/process",
        json={},
        headers={"Idempotency-Key": key},
    )
    assert started.status_code == 202, started.text
    assert client.portal is not None
    with pytest.raises(APIError):
        client.portal.call(app.state.pipeline.run, uuid.UUID(started.json()["id"]))
    response = client.get(f"/api/v1/jobs/{started.json()['id']}")
    assert response.status_code == 200
    return response.json()


def test_invalid_media_bytes_are_rejected_by_background_validation(client: TestClient, app) -> None:
    create_session(client)
    project = create_project(client)
    invalid = b"not actually a wave file"
    presign = client.post(
        f"/api/v1/projects/{project['id']}/uploads/presign",
        json={
            "filename": "fake.wav",
            "contentType": "audio/wav",
            "sizeBytes": len(invalid),
            "rightToUploadConfirmed": True,
        },
    )
    assert presign.status_code == 201
    signed = presign.json()
    assert (
        client.put(
            signed["uploadUrl"],
            content=invalid,
            headers=signed["requiredHeaders"],
        ).status_code
        == 204
    )
    complete = client.post(f"/api/v1/uploads/{signed['assetId']}/complete", json={})
    assert complete.status_code == 200
    assert complete.json()["status"] == "UPLOADED"
    failed = _run_failed_validation(client, app, project["id"], "invalid-audio")
    assert failed["stage"] == "FAILED"
    assert failed["errorCode"] == "INVALID_AUDIO"


def test_duration_limit_uses_queued_probe_not_client_metadata(
    client: TestClient, app, settings
) -> None:
    create_session(client)
    project = create_project(client)
    # A tiny 10 Hz PCM file can still represent a duration beyond the policy limit.
    audio = wav_bytes(settings.max_audio_duration_seconds + 1, sample_rate=10)
    presign = client.post(
        f"/api/v1/projects/{project['id']}/uploads/presign",
        json={
            "filename": "long.wav",
            "contentType": "audio/wav",
            "sizeBytes": len(audio),
            "rightToUploadConfirmed": True,
        },
    ).json()
    assert (
        client.put(
            presign["uploadUrl"], content=audio, headers=presign["requiredHeaders"]
        ).status_code
        == 204
    )
    response = client.post(f"/api/v1/uploads/{presign['assetId']}/complete", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "UPLOADED"
    failed = _run_failed_validation(client, app, project["id"], "too-long")
    assert failed["stage"] == "FAILED"
    assert failed["errorCode"] == "AUDIO_TOO_LONG"


def test_signed_url_expiry_and_tampering(settings) -> None:
    storage = LocalPrivateStorage(settings)
    key = "users/test/projects/test/originals/object"
    expires = 1_900_000_000
    signature = storage._signature("GET", key, expires)  # exercise exact verifier contract
    assert storage.verify_signature(
        method="GET", key=key, expires=expires, signature=signature, now_epoch=expires
    )
    assert not storage.verify_signature(
        method="GET", key=key, expires=expires, signature=signature, now_epoch=expires + 1
    )
    assert not storage.verify_signature(
        method="GET",
        key=key + "-tampered",
        expires=expires,
        signature=signature,
        now_epoch=expires,
    )


def test_audio_signature_sniffing_does_not_trust_extension() -> None:
    assert sniff_content_type(wav_bytes()[:64]) == "audio/wav"
    assert sniff_content_type(b"malware.exe") is None


def test_s3_presigned_urls_use_browser_reachable_endpoint() -> None:
    storage = S3PrivateStorage(
        Settings(
            storage_backend="s3",
            s3_endpoint_url="http://minio:9000",
            s3_public_endpoint_url="http://localhost:9000",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            s3_bucket="private",
        )
    )
    put = asyncio.run(storage.presign_put("users/u/object", "audio/wav", 44, 60))
    get = asyncio.run(storage.presign_get("users/u/object", 60))
    assert urlparse(put.url).netloc == "localhost:9000"
    assert urlparse(get.url).netloc == "localhost:9000"
    assert "minio" not in put.url
    assert put.required_headers["x-amz-server-side-encryption"] == "AES256"
    assert "Content-Length" not in put.required_headers
    cors = storage.browser_cors_configuration(["http://localhost:3000"])
    rule = cors["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["http://localhost:3000"]
    assert rule["AllowedMethods"] == ["GET", "HEAD", "PUT"]
    assert rule["ExposeHeaders"] == ["ETag"]
    with pytest.raises(ValueError, match="explicit"):
        storage.browser_cors_configuration(["*"])


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://account.r2.cloudflarestorage.com",
        "https://br-production.storage.c-2.us-east-2.aws.neon.tech",
    ],
)
def test_managed_s3_providers_omit_unsupported_aws_encryption_header(endpoint: str) -> None:
    storage = S3PrivateStorage(
        Settings(
            storage_backend="s3",
            s3_endpoint_url=endpoint,
            s3_public_endpoint_url=endpoint,
            s3_region="auto",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            s3_bucket="drumscribe-private",
        )
    )
    put = asyncio.run(storage.presign_put("users/u/object", "audio/wav", 44, 60))
    assert storage.server_side_encryption is None
    assert "x-amz-server-side-encryption" not in put.required_headers
    assert "x-amz-server-side-encryption" not in urlparse(put.url).query
    cors = storage.browser_cors_configuration(["https://drumscribe.example"])
    assert cors["CORSRules"][0]["AllowedHeaders"] == ["content-type"]


def test_neon_storage_uses_file_copy_fallback() -> None:
    storage = S3PrivateStorage(
        Settings(
            storage_backend="s3",
            s3_endpoint_url="https://br-production.storage.c-2.us-east-2.aws.neon.tech",
            s3_public_endpoint_url=("https://br-production.storage.c-2.us-east-2.aws.neon.tech"),
            s3_region="us-east-2",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            s3_bucket="drumscribe-private",
        )
    )

    class FakeClient:
        def __init__(self) -> None:
            self.copy_called = False
            self.uploaded = b""

        def copy_object(self, **kwargs):
            self.copy_called = True

        def download_file(self, bucket, key, filename):
            del bucket, key
            Path(filename).write_bytes(b"private-audio")

        def upload_file(self, filename, bucket, key, ExtraArgs):
            del bucket, key
            assert ExtraArgs == {"ContentType": "audio/wav"}
            self.uploaded = Path(filename).read_bytes()

    fake = FakeClient()
    storage.client = fake
    asyncio.run(storage.copy("source/audio", "destination/audio", "audio/wav"))
    assert fake.copy_called is False
    assert fake.uploaded == b"private-audio"


def test_s3_deletes_are_batched_and_partial_failures_are_not_ignored() -> None:
    storage = S3PrivateStorage(
        Settings(
            storage_backend="s3",
            s3_endpoint_url="http://minio:9000",
            s3_public_endpoint_url="http://localhost:9000",
            s3_access_key_id="test-access",
            s3_secret_access_key="test-secret",
            s3_bucket="private",
        )
    )

    class FakeClient:
        def __init__(self) -> None:
            self.batch_sizes: list[int] = []

        def delete_objects(self, **kwargs):
            objects = kwargs["Delete"]["Objects"]
            self.batch_sizes.append(len(objects))
            if len(self.batch_sizes) == 2:
                return {"Errors": [{"Key": objects[0]["Key"], "Code": "InternalError"}]}
            return {}

    fake = FakeClient()
    storage.client = fake
    with pytest.raises(RuntimeError, match="failed to delete"):
        asyncio.run(storage.delete_many([f"objects/{index}" for index in range(1_001)]))
    assert fake.batch_sizes == [1_000, 1]
