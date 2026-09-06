import json
from collections.abc import Iterator

import pytest

from drumscribe_api import ops


def test_purge_expired_data_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def fake_purge() -> dict[str, int]:
        return {"assets": 2, "expiredExports": 1}

    monkeypatch.setattr(ops, "_purge_expired_data", fake_purge)

    assert ops.main(["purge-expired-data"]) == 0
    assert json.loads(capsys.readouterr().out) == {"assets": 2, "expiredExports": 1}


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    ops.get_settings.cache_clear()
    yield
    ops.get_settings.cache_clear()
