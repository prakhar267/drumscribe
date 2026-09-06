import argparse
import asyncio
import json
from collections.abc import Sequence

from .config import get_settings
from .database import Database
from .services.retention import RetentionService
from .services.storage import create_storage


async def _purge_expired_data() -> dict[str, int]:
    settings = get_settings()
    database = Database(settings)
    try:
        return await RetentionService(settings, database, create_storage(settings)).run()
    finally:
        await database.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DrumScribe production operations")
    parser.add_argument(
        "operation",
        choices=("purge-expired-data",),
        help="Idempotent operation to run",
    )
    args = parser.parse_args(argv)
    if args.operation == "purge-expired-data":
        print(json.dumps(asyncio.run(_purge_expired_data()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
