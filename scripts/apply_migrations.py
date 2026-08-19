"""Apply SQL files from supabase/migrations in filename order.

Used by Docker and local start when the Supabase CLI is not available.
Tracks applied versions in supabase_migrations.schema_migrations so
`supabase db push` stays compatible.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from app.core.database import SessionFactory, engine
from app.core.logging import configure_logging, get_logger
from sqlalchemy import text

logger = get_logger("aahaar.migrate")

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"
VERSION_RE = re.compile(r"^(\d{14})_(.+)\.sql$")
INITIAL_VERSION = "20260816152546"


def migration_files() -> list[tuple[str, str, Path]]:
    files: list[tuple[str, str, Path]] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        match = VERSION_RE.match(path.name)
        if not match:
            raise SystemExit(f"Invalid migration filename: {path.name}")
        files.append((match.group(1), match.group(2), path))
    return files


async def ensure_history() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("create schema if not exists supabase_migrations"))
        await conn.execute(
            text(
                """
                create table if not exists supabase_migrations.schema_migrations (
                  version text primary key,
                  statements text[],
                  name text
                )
                """
            )
        )


async def applied_versions() -> set[str]:
    async with SessionFactory() as session:
        result = await session.execute(
            text("select version from supabase_migrations.schema_migrations")
        )
        return {row[0] for row in result.all()}


async def table_exists(name: str) -> bool:
    async with SessionFactory() as session:
        result = await session.execute(
            text("select to_regclass(:rel) is not null"),
            {"rel": f"public.{name}"},
        )
        return bool(result.scalar())


async def stamp(version: str, name: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                insert into supabase_migrations.schema_migrations (version, name)
                values (:version, :name)
                on conflict (version) do nothing
                """
            ),
            {"version": version, "name": name},
        )


async def execute_script(sql: str) -> None:
    """Run a multi-statement file on the raw asyncpg connection.

    SQLAlchemy/asyncpg prepared statements reject more than one command.
    """
    async with engine.begin() as conn:
        raw = await conn.get_raw_connection()
        driver = raw.driver_connection
        await driver.execute(sql)


async def apply_one(version: str, name: str, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    logger.info("Applying %s_%s", version, name)
    await execute_script(sql)
    await stamp(version, name)


async def main() -> None:
    if not MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"Missing migrations folder: {MIGRATIONS_DIR}")
    await ensure_history()
    done = await applied_versions()
    has_schema = await table_exists("tenants")
    pending = [item for item in migration_files() if item[0] not in done]
    if not pending:
        logger.info("No pending migrations.")
        await engine.dispose()
        return
    for version, name, path in pending:
        if version == INITIAL_VERSION and has_schema:
            logger.info("Existing schema found; recording %s_%s", version, name)
            await stamp(version, name)
            continue
        await apply_one(version, name, path)
    logger.info("Applied %s migration(s).", len(pending))
    await engine.dispose()


if __name__ == "__main__":
    configure_logging(debug=True)
    asyncio.run(main())
