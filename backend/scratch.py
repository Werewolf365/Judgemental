"""Dev probe: verify the participant_registrations table exists and is readable.

Usage (from the repo root):
    docker compose exec -T api python scratch.py

Uses the same DATABASE_URL as the app, so it works wherever the app runs.
Exit code 0 = table OK, 1 = anything wrong.
"""
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://dogfood:dogfood@db:5432/dogfood"
)


async def main() -> int:
    try:
        engine = create_async_engine(DATABASE_URL)
        async with engine.connect() as conn:
            res = await conn.execute(
                text("SELECT * FROM participant_registrations LIMIT 1"))
            print("Table exists, row:", res.fetchone())
            await engine.dispose()
        return 0
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
