import asyncio
import base64
import contextlib
import os
import shutil
import tempfile
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode

import anyio
import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from ..config import Settings
from ..security import sign_value, signatures_match


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    size_bytes: int
    content_type: str | None
    etag: str | None


@dataclass(frozen=True, slots=True)
class PresignedRequest:
    url: str
    expires_at_epoch: int
    required_headers: dict[str, str]


class ObjectNotFoundError(Exception):
    pass


class PrivateStorage(Protocol):
    async def presign_put(
        self, key: str, content_type: str, size_bytes: int, expires_in: int
    ) -> PresignedRequest: ...

    async def presign_get(self, key: str, expires_in: int) -> PresignedRequest: ...

    async def head(self, key: str) -> ObjectMetadata: ...

    async def read_prefix(self, key: str, length: int = 65_536) -> bytes: ...

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...

    async def put_file(self, key: str, source: Path, content_type: str) -> None: ...

    async def copy(self, source_key: str, destination_key: str, content_type: str) -> None: ...

    async def delete_many(self, keys: list[str]) -> None: ...

    def materialize(self, key: str) -> contextlib.AbstractAsyncContextManager[Path]: ...


def _validate_key(key: str) -> str:
    normalized = key.replace("\\", "/").strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("invalid object key")
    return normalized


class LocalPrivateStorage:
    """Private filesystem adapter with expiring HMAC routes for local development/tests."""

    def __init__(self, settings: Settings) -> None:
        self.root = settings.local_storage_path.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_api_url = settings.public_api_url.rstrip("/")
        self.secret = settings.session_secret_bytes

    def path_for(self, key: str) -> Path:
        safe_key = _validate_key(key)
        path = (self.root / safe_key).resolve()
        if self.root not in path.parents:
            raise ValueError("object key escapes storage root")
        return path

    def _signature(
        self,
        method: str,
        key: str,
        expires: int,
        content_type: str = "",
        size_bytes: int | str = "",
    ) -> str:
        canonical = f"{method}\n{_validate_key(key)}\n{expires}\n{content_type}\n{size_bytes}"
        return sign_value(canonical, self.secret)

    def verify_signature(
        self,
        *,
        method: str,
        key: str,
        expires: int,
        signature: str,
        content_type: str = "",
        size_bytes: int | str = "",
        now_epoch: int | None = None,
    ) -> bool:
        now = int(time.time()) if now_epoch is None else now_epoch
        if expires < now:
            return False
        expected = self._signature(method, key, expires, content_type, size_bytes)
        return signatures_match(signature, expected)

    @staticmethod
    def encode_key(key: str) -> str:
        return base64.urlsafe_b64encode(_validate_key(key).encode()).decode().rstrip("=")

    @staticmethod
    def decode_key(encoded: str) -> str:
        padding = "=" * (-len(encoded) % 4)
        return _validate_key(base64.urlsafe_b64decode(encoded + padding).decode())

    async def presign_put(
        self, key: str, content_type: str, size_bytes: int, expires_in: int
    ) -> PresignedRequest:
        expires = int(time.time()) + expires_in
        signature = self._signature("PUT", key, expires, content_type, size_bytes)
        query = urlencode(
            {
                "expires": expires,
                "signature": signature,
                "contentType": content_type,
                "size": size_bytes,
            }
        )
        url = (
            f"{self.public_api_url}/api/v1/storage/local/{self.encode_key(key)}?{query}"
        )
        return PresignedRequest(
            url=url,
            expires_at_epoch=expires,
            required_headers={"Content-Type": content_type},
        )

    async def presign_get(self, key: str, expires_in: int) -> PresignedRequest:
        expires = int(time.time()) + expires_in
        signature = self._signature("GET", key, expires)
        query = urlencode({"expires": expires, "signature": signature})
        url = (
            f"{self.public_api_url}/api/v1/storage/local/{self.encode_key(key)}?{query}"
        )
        return PresignedRequest(url=url, expires_at_epoch=expires, required_headers={})

    async def write_stream(
        self,
        key: str,
        chunks: AsyncIterator[bytes],
        *,
        expected_size: int,
        max_size: int,
    ) -> int:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.upload")
        written = 0
        try:
            async with await anyio.open_file(temporary, "wb") as handle:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_size or written > expected_size:
                        raise ValueError("upload exceeds signed size")
                    await handle.write(chunk)
            if written != expected_size:
                raise ValueError("upload size differs from signed size")
            temporary.replace(path)
            return written
        finally:
            if temporary.exists():
                temporary.unlink()

    async def head(self, key: str) -> ObjectMetadata:
        path = self.path_for(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        return ObjectMetadata(size_bytes=path.stat().st_size, content_type=None, etag=None)

    async def read_prefix(self, key: str, length: int = 65_536) -> bytes:
        path = self.path_for(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        async with await anyio.open_file(path, "rb") as handle:
            return await handle.read(length)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        del content_type
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        async with await anyio.open_file(path, "wb") as handle:
            await handle.write(data)

    async def put_file(self, key: str, source: Path, content_type: str) -> None:
        del content_type
        destination = self.path_for(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)

    async def copy(self, source_key: str, destination_key: str, content_type: str) -> None:
        del content_type
        source = self.path_for(source_key)
        destination = self.path_for(destination_key)
        if not source.is_file():
            raise ObjectNotFoundError(source_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)

    async def delete_many(self, keys: list[str]) -> None:
        for key in keys:
            path = self.path_for(key)
            if path.is_file():
                await asyncio.to_thread(path.unlink)

    @contextlib.asynccontextmanager
    async def materialize(self, key: str) -> AsyncIterator[Path]:
        path = self.path_for(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        yield path


class S3PrivateStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        credentials = {
            "region_name": settings.s3_region,
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": (
                settings.s3_secret_access_key.get_secret_value()
                if settings.s3_secret_access_key
                else None
            ),
            "config": Config(signature_version="s3v4"),
        }
        # Server-side operations use the private service address; URLs handed to browsers
        # must be signed with the separately configured browser-reachable endpoint.
        self.client: Any = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint_url, **credentials
        )
        public_endpoint = settings.s3_public_endpoint_url or settings.s3_endpoint_url
        self.signing_client: Any = boto3.client(
            "s3", endpoint_url=public_endpoint, **credentials
        )

    @staticmethod
    def browser_cors_configuration(origins: list[str]) -> dict[str, Any]:
        clean_origins = sorted({origin.rstrip("/") for origin in origins if origin.strip()})
        if not clean_origins or "*" in clean_origins:
            raise ValueError("S3 browser CORS requires explicit web origins")
        return {
            "CORSRules": [
                {
                    "AllowedOrigins": clean_origins,
                    "AllowedMethods": ["GET", "HEAD", "PUT"],
                    "AllowedHeaders": [
                        "content-type",
                        "x-amz-server-side-encryption",
                    ],
                    "ExposeHeaders": ["ETag"],
                    "MaxAgeSeconds": 600,
                }
            ]
        }

    async def configure_browser_cors(self, origins: list[str]) -> None:
        await asyncio.to_thread(
            self.client.put_bucket_cors,
            Bucket=self.bucket,
            CORSConfiguration=self.browser_cors_configuration(origins),
        )

    async def presign_put(
        self, key: str, content_type: str, size_bytes: int, expires_in: int
    ) -> PresignedRequest:
        safe_key = _validate_key(key)
        params = {
            "Bucket": self.bucket,
            "Key": safe_key,
            "ContentType": content_type,
            "ServerSideEncryption": "AES256",
        }
        url = self.signing_client.generate_presigned_url(
            "put_object", Params=params, ExpiresIn=expires_in, HttpMethod="PUT"
        )
        return PresignedRequest(
            url=url,
            expires_at_epoch=int(time.time()) + expires_in,
            required_headers={
                "Content-Type": content_type,
                "x-amz-server-side-encryption": "AES256",
            },
        )

    async def presign_get(self, key: str, expires_in: int) -> PresignedRequest:
        url = self.signing_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": _validate_key(key)},
            ExpiresIn=expires_in,
            HttpMethod="GET",
        )
        return PresignedRequest(
            url=url, expires_at_epoch=int(time.time()) + expires_in, required_headers={}
        )

    async def head(self, key: str) -> ObjectMetadata:
        try:
            result = await asyncio.to_thread(
                self.client.head_object, Bucket=self.bucket, Key=_validate_key(key)
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                raise ObjectNotFoundError(key) from exc
            raise
        return ObjectMetadata(
            size_bytes=int(result["ContentLength"]),
            content_type=result.get("ContentType"),
            etag=result.get("ETag", "").strip('"') or None,
        )

    async def read_prefix(self, key: str, length: int = 65_536) -> bytes:
        try:
            result = await asyncio.to_thread(
                self.client.get_object,
                Bucket=self.bucket,
                Key=_validate_key(key),
                Range=f"bytes=0-{length - 1}",
            )
        except ClientError as exc:
            raise ObjectNotFoundError(key) from exc
        return await asyncio.to_thread(result["Body"].read)

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=_validate_key(key),
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )

    async def put_file(self, key: str, source: Path, content_type: str) -> None:
        await asyncio.to_thread(
            self.client.upload_file,
            str(source),
            self.bucket,
            _validate_key(key),
            ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"},
        )

    async def copy(self, source_key: str, destination_key: str, content_type: str) -> None:
        try:
            await asyncio.to_thread(
                self.client.copy_object,
                Bucket=self.bucket,
                Key=_validate_key(destination_key),
                CopySource={"Bucket": self.bucket, "Key": _validate_key(source_key)},
                ContentType=content_type,
                MetadataDirective="REPLACE",
                ServerSideEncryption="AES256",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                raise ObjectNotFoundError(source_key) from exc
            raise

    async def delete_many(self, keys: list[str]) -> None:
        if not keys:
            return
        safe_keys = [_validate_key(key) for key in keys]
        for offset in range(0, len(safe_keys), 1_000):
            batch = safe_keys[offset : offset + 1_000]
            result = await asyncio.to_thread(
                self.client.delete_objects,
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
            )
            errors = result.get("Errors", [])
            if errors:
                failed = ", ".join(str(error.get("Key", "unknown")) for error in errors[:5])
                raise RuntimeError(f"S3 failed to delete private objects: {failed}")

    @contextlib.asynccontextmanager
    async def materialize(self, key: str) -> AsyncIterator[Path]:
        handle = tempfile.NamedTemporaryFile(prefix="drumscribe-", suffix=".audio", delete=False)
        path = Path(handle.name)
        handle.close()
        try:
            await asyncio.to_thread(
                self.client.download_file, self.bucket, _validate_key(key), str(path)
            )
            yield path
        finally:
            await asyncio.to_thread(path.unlink, missing_ok=True)


def create_storage(settings: Settings) -> PrivateStorage:
    if settings.storage_backend == "s3":
        return S3PrivateStorage(settings)
    return LocalPrivateStorage(settings)
