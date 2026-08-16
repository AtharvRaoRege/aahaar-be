"""Block until the database accepts connections (used by the Docker entrypoint)."""

from __future__ import annotations

import asyncio
import sys

from app.core.database import engine
from app.core.logging import configure_logging, get_logger
from sqlalchemy import text

logger = get_logger("aahaar.waitdb")

MAX_ATTEMPTS = 30
DELAY_SECONDS = 2


async def wait() -> bool:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database is ready.")
            return True
        except Exception as exc:
            logger.info("DB not ready (attempt %s/%s): %s", attempt, MAX_ATTEMPTS, exc)
            await asyncio.sleep(DELAY_SECONDS)
    return False


if __name__ == "__main__":
    configure_logging(debug=True)
    ok = asyncio.run(wait())
    sys.exit(0 if ok else 1)
