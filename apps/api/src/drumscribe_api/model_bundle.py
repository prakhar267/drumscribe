"""Build, publish, and install DrumScribe's private production model bundle.

The public application repository deliberately excludes first-party checkpoints.
Release tooling stores them as one hash-pinned archive in private S3-compatible
storage. Workers verify both the archive and every member before installing it.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

BUNDLE_SCHEMA_VERSION = 1
DEFAULT_MAX_BUNDLE_BYTES = 128 * 1024 * 1024
MANIFEST_NAME = "manifest.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# These are the only private first-party checkpoints loaded by the production v6
# ensemble. A changed checkpoint must go through the model approval process and
# update both the ensemble config and this fail-closed deployment allowlist.
APPROVED_CHECKPOINTS: dict[str, str] = {
    "data/licensed-corpus/experiments/groove-oaf-open-cymbal-specialist-v15/"
    "checkpoint-0014.pt": "52d5ac17883fe384b18e4020f9d431a5f07b23805e7b897a134bf7399b655157",
    "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/"
    "checkpoint-0003.pt": "7c05b837d033206e80aa638261dfa633caf7e1d60029acfa77f7150dbd1fea81",
    "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v9/"
    "checkpoint-0004.pt": "d193330ccaa794b042599889d99e3c6479e2cb970ca0454a64234e337c7a5bcd",
    "data/licensed-corpus/experiments/groove-oaf-articulation-specialist-v14/"
    "checkpoint-0015.pt": "89538ed53ad0395c8b41f1aba2a1ea0b5a6228e04ed441ffdb1b08550e3345e8",
    "data/licensed-corpus/experiments/groove-oaf-cnn-articulation-v10/"
    "best.pt": "23a9057d2df6bccde14bce72c280f0bbdbe23236ed4c6e785f2e3496f198ff00",
    "data/licensed-corpus/experiments/groove-oaf-family-finetune-v12/"
    "best.pt": "57873926129a421d265b4102727f886b68dfbb5b1ea7c10f98280591e588c182",
    "data/licensed-corpus/experiments/groove-egmd-spectral-moe-v7/"
    "best.pt": "b98fe251d7c269fb18dd3474be0109aef1bd6c16b4ee9412308388eae1343625",
    "data/licensed-corpus/experiments/groove-egmd-weak-class-specialist-v17/"
    "checkpoint-0015.pt": "e81c51262daca78d378b6c9fbc349001f70d36180667c4926437603041ca26ac",
}


class ModelBundleError(RuntimeError):
    """A model bundle is missing, untrusted, or malformed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_manifest(files: list[dict[str, Any]]) -> bytes:
    payload = {
        "schemaVersion": BUNDLE_SCHEMA_VERSION,
        "modelVersion": "drumscribe-recall-fusion-v6",
        "files": files,
    }
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _tar_info(name: str, size: int, *, mode: int = 0o600) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mode = mode
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def build_bundle(
    repository: Path,
    output: Path,
    *,
    expected_files: Mapping[str, str] = APPROVED_CHECKPOINTS,
) -> str:
    """Create a reproducible archive and return its SHA-256 digest."""

    repository = repository.resolve(strict=True)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    sources: list[tuple[str, Path]] = []
    for relative, expected_sha256 in sorted(expected_files.items()):
        _validated_relative_path(relative)
        if not SHA256_PATTERN.fullmatch(expected_sha256):
            raise ModelBundleError(f"invalid approved SHA-256 for {relative}")
        source = (repository / relative).resolve(strict=True)
        if repository not in source.parents or not source.is_file():
            raise ModelBundleError(
                f"approved checkpoint is not a regular repository file: {relative}"
            )
        actual_sha256 = sha256_file(source)
        if actual_sha256 != expected_sha256:
            raise ModelBundleError(
                f"approved checkpoint hash mismatch for {relative}: {actual_sha256}"
            )
        size = source.stat().st_size
        files.append({"path": relative, "sha256": actual_sha256, "sizeBytes": size})
        sources.append((relative, source))

    manifest = _canonical_manifest(files)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.partial")
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    archive.addfile(_tar_info(MANIFEST_NAME, len(manifest)), io.BytesIO(manifest))
                    for relative, source in sources:
                        with source.open("rb") as handle:
                            archive.addfile(_tar_info(relative, source.stat().st_size), handle)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_file(output)


def _validated_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ModelBundleError(f"unsafe model bundle path: {value!r}")
    return path


def _target(root: Path, relative: str) -> Path:
    path = _validated_relative_path(relative)
    target = (root / Path(*path.parts)).resolve()
    if root != target and root not in target.parents:
        raise ModelBundleError(f"model bundle path escapes installation root: {relative!r}")
    return target


def _read_manifest(archive: tarfile.TarFile) -> dict[str, Any]:
    try:
        member = archive.getmember(MANIFEST_NAME)
    except KeyError as exc:
        raise ModelBundleError("model bundle manifest is missing") from exc
    if not member.isfile() or member.size > 1024 * 1024:
        raise ModelBundleError("model bundle manifest is invalid")
    handle = archive.extractfile(member)
    if handle is None:
        raise ModelBundleError("model bundle manifest is unreadable")
    try:
        payload = json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ModelBundleError("model bundle manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ModelBundleError("model bundle manifest must be an object")
    return payload


def _validated_manifest(
    payload: dict[str, Any], expected_files: Mapping[str, str]
) -> dict[str, tuple[str, int]]:
    if payload.get("schemaVersion") != BUNDLE_SCHEMA_VERSION:
        raise ModelBundleError("model bundle schema version is unsupported")
    if payload.get("modelVersion") != "drumscribe-recall-fusion-v6":
        raise ModelBundleError("model bundle version is not production approved")
    raw_files = payload.get("files")
    if not isinstance(raw_files, list):
        raise ModelBundleError("model bundle file manifest is invalid")
    files: dict[str, tuple[str, int]] = {}
    for raw in raw_files:
        if not isinstance(raw, dict):
            raise ModelBundleError("model bundle file entry is invalid")
        relative = str(raw.get("path", ""))
        _validated_relative_path(relative)
        digest = str(raw.get("sha256", ""))
        size = raw.get("sizeBytes")
        if relative in files or not SHA256_PATTERN.fullmatch(digest):
            raise ModelBundleError(f"model bundle file entry is invalid: {relative!r}")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ModelBundleError(f"model bundle file size is invalid: {relative!r}")
        files[relative] = (digest, size)
    if set(files) != set(expected_files) or any(
        files[path][0] != digest for path, digest in expected_files.items() if path in files
    ):
        raise ModelBundleError("model bundle files do not match the production allowlist")
    return files


def install_bundle(
    bundle: Path,
    root: Path,
    *,
    expected_files: Mapping[str, str] = APPROVED_CHECKPOINTS,
) -> bool:
    """Verify and atomically install a local bundle; return whether files changed."""

    bundle = bundle.expanduser().resolve(strict=True)
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, mode="r:gz") as archive:
        members = archive.getmembers()
        if len({member.name for member in members}) != len(members):
            raise ModelBundleError("model bundle contains duplicate members")
        manifest = _validated_manifest(_read_manifest(archive), expected_files)
        if set(member.name for member in members) != {MANIFEST_NAME, *manifest}:
            raise ModelBundleError("model bundle contains unexpected members")
        if all(
            (target := _target(root, relative)).is_file()
            and target.stat().st_size == size
            and sha256_file(target) == digest
            for relative, (digest, size) in manifest.items()
        ):
            return False

        with tempfile.TemporaryDirectory(prefix="drumscribe-model-bundle-", dir=root) as directory:
            stage = Path(directory)
            for relative, (expected_sha256, expected_size) in manifest.items():
                member = archive.getmember(relative)
                if not member.isfile() or member.size != expected_size:
                    raise ModelBundleError(f"model bundle member is invalid: {relative}")
                source = archive.extractfile(member)
                if source is None:
                    raise ModelBundleError(f"model bundle member is unreadable: {relative}")
                destination = _target(stage, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                written = 0
                with destination.open("wb") as handle:
                    while chunk := source.read(1024 * 1024):
                        written += len(chunk)
                        if written > expected_size:
                            raise ModelBundleError(f"model bundle member is oversized: {relative}")
                        digest.update(chunk)
                        handle.write(chunk)
                if written != expected_size or digest.hexdigest() != expected_sha256:
                    raise ModelBundleError(f"model bundle member hash mismatch: {relative}")
            for relative in manifest:
                destination = _target(root, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                _target(stage, relative).replace(destination)
    return True


def _s3_client() -> Any:
    endpoint = _required_environment("DRUMSCRIBE_S3_ENDPOINT_URL")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("DRUMSCRIBE_S3_REGION", "us-east-1"),
        aws_access_key_id=_required_environment("DRUMSCRIBE_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=_required_environment("DRUMSCRIBE_S3_SECRET_ACCESS_KEY"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ModelBundleError(f"required environment variable is missing: {name}")
    return value


def publish_bundle(bundle: Path, object_key: str) -> None:
    bundle = bundle.expanduser().resolve(strict=True)
    _validated_relative_path(object_key)
    _s3_client().upload_file(
        os.fspath(bundle),
        _required_environment("DRUMSCRIBE_S3_BUCKET"),
        object_key,
        ExtraArgs={"ContentType": "application/gzip"},
    )


def download_bundle(destination: Path, *, maximum_bytes: int) -> None:
    if maximum_bytes <= 0:
        raise ModelBundleError("maximum model bundle size must be positive")
    object_key = _required_environment("DRUMSCRIBE_MODEL_BUNDLE_KEY")
    _validated_relative_path(object_key)
    expected_sha256 = _required_environment("DRUMSCRIBE_MODEL_BUNDLE_SHA256").lower()
    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise ModelBundleError("DRUMSCRIBE_MODEL_BUNDLE_SHA256 must be a lowercase SHA-256")
    client = _s3_client()
    bucket = _required_environment("DRUMSCRIBE_S3_BUCKET")
    metadata = client.head_object(Bucket=bucket, Key=object_key)
    size = int(metadata.get("ContentLength", 0))
    if size <= 0 or size > maximum_bytes:
        raise ModelBundleError(f"model bundle size is outside the allowed range: {size}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.partial")
    try:
        with temporary.open("wb") as handle:
            body = client.get_object(Bucket=bucket, Key=object_key)["Body"]
            shutil.copyfileobj(body, handle, length=1024 * 1024)
        if temporary.stat().st_size != size or sha256_file(temporary) != expected_sha256:
            raise ModelBundleError("downloaded model bundle failed its SHA-256 check")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build the private checkpoint archive")
    build.add_argument("--repository", type=Path, default=Path.cwd())
    build.add_argument("--output", type=Path, required=True)

    publish = subparsers.add_parser("publish", help="upload an existing archive")
    publish.add_argument("--bundle", type=Path, required=True)
    publish.add_argument("--object-key", required=True)

    install = subparsers.add_parser("install", help="download, verify, and install an archive")
    install.add_argument("--root", type=Path, default=Path("/app"))
    install.add_argument(
        "--maximum-bytes",
        type=_positive_integer,
        default=DEFAULT_MAX_BUNDLE_BYTES,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "build":
        digest = build_bundle(args.repository, args.output)
        print(json.dumps({"bundle": os.fspath(args.output), "sha256": digest}, sort_keys=True))
        return 0
    if args.command == "publish":
        publish_bundle(args.bundle, args.object_key)
        print(json.dumps({"objectKey": args.object_key, "status": "published"}, sort_keys=True))
        return 0

    root = args.root.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="drumscribe-model-download-", dir=root) as directory:
        bundle = Path(directory) / "models.tar.gz"
        download_bundle(bundle, maximum_bytes=args.maximum_bytes)
        changed = install_bundle(bundle, root)
    print(json.dumps({"modelBundleInstalled": changed, "status": "ready"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
