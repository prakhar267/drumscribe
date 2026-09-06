import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from drumscribe_api.model_bundle import ModelBundleError, build_bundle, install_bundle


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_build_and_install_bundle_is_reproducible_and_idempotent(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    source = repository / "data" / "models" / "checkpoint.pt"
    source.parent.mkdir(parents=True)
    payload = b"private-model-checkpoint"
    source.write_bytes(payload)
    expected = {"data/models/checkpoint.pt": _sha256(payload)}
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"

    first_digest = build_bundle(repository, first, expected_files=expected)
    second_digest = build_bundle(repository, second, expected_files=expected)

    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()
    destination = tmp_path / "runtime"
    assert install_bundle(first, destination, expected_files=expected) is True
    assert (destination / "data/models/checkpoint.pt").read_bytes() == payload
    assert install_bundle(first, destination, expected_files=expected) is False


def test_install_bundle_rejects_member_with_changed_bytes(tmp_path: Path) -> None:
    path = "data/models/checkpoint.pt"
    approved = b"approved"
    changed = b"tampered"
    expected = {path: _sha256(approved)}
    manifest = {
        "schemaVersion": 1,
        "modelVersion": "drumscribe-recall-fusion-v6",
        "files": [{"path": path, "sha256": _sha256(approved), "sizeBytes": len(changed)}],
    }
    bundle = tmp_path / "tampered.tar.gz"
    with tarfile.open(bundle, "w:gz") as archive:
        manifest_bytes = json.dumps(manifest).encode()
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest_bytes)
        archive.addfile(info, io.BytesIO(manifest_bytes))
        info = tarfile.TarInfo(path)
        info.size = len(changed)
        archive.addfile(info, io.BytesIO(changed))

    with pytest.raises(ModelBundleError, match="hash mismatch"):
        install_bundle(bundle, tmp_path / "runtime", expected_files=expected)


def test_install_bundle_rejects_path_traversal_before_writing(tmp_path: Path) -> None:
    path = "../outside.pt"
    payload = b"model"
    manifest = {
        "schemaVersion": 1,
        "modelVersion": "drumscribe-recall-fusion-v6",
        "files": [{"path": path, "sha256": _sha256(payload), "sizeBytes": len(payload)}],
    }
    bundle = tmp_path / "unsafe.tar.gz"
    with bundle.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb") as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                manifest_bytes = json.dumps(manifest).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size = len(manifest_bytes)
                archive.addfile(info, io.BytesIO(manifest_bytes))
                info = tarfile.TarInfo(path)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

    with pytest.raises(ModelBundleError, match="unsafe model bundle path"):
        install_bundle(bundle, tmp_path / "runtime", expected_files={path: _sha256(payload)})
    assert not (tmp_path / "outside.pt").exists()
