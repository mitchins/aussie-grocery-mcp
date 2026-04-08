"""SQLite cache with per-table TTLs for Woolworths data."""

import json
import logging
import time
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SEARCH_TTL = 7200  # 2 hours
PRODUCT_TTL = 7200  # 2 hours
NUTRITION_TTL = 2_592_000  # 30 days

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS search_cache (
    key        TEXT PRIMARY KEY,
    data_json  TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS product_cache (
    stockcode  INTEGER PRIMARY KEY,
    data_json  TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS nutrition_cache (
    stockcode  INTEGER PRIMARY KEY,
    data_json  TEXT NOT NULL,
    cached_at  REAL NOT NULL
);
"""


class Cache:
    def __init__(self, db_path: str = "cache.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.executescript(_INIT_SQL)
        return self._db

    # ── generic helpers ───────────────────────────────────────────────

    async def _get(self, table: str, key_col: str, key_val: Any, ttl: float) -> dict | None:
        db = await self._get_db()
        sql = f"SELECT data_json, cached_at FROM {table} WHERE {key_col} = ?"
        async with db.execute(sql, (key_val,)) as cur:
            row = await cur.fetchone()
        if row and (time.time() - row[1]) < ttl:
            return json.loads(row[0])
        return None

    async def _set(self, table: str, key_col: str, key_val: Any, data: dict) -> None:
        db = await self._get_db()
        sql = (
            f"INSERT OR REPLACE INTO {table} ({key_col}, data_json, cached_at) "
            "VALUES (?, ?, ?)"
        )
        await db.execute(sql, (key_val, json.dumps(data), time.time()))
        await db.commit()

    # ── public API ────────────────────────────────────────────────────

    async def get_search(self, key: str) -> dict | None:
        return await self._get("search_cache", "key", key, SEARCH_TTL)

    async def set_search(self, key: str, data: dict) -> None:
        await self._set("search_cache", "key", key, data)

    async def get_product(self, stockcode: int) -> dict | None:
        return await self._get("product_cache", "stockcode", stockcode, PRODUCT_TTL)

    async def set_product(self, stockcode: int, data: dict) -> None:
        await self._set("product_cache", "stockcode", stockcode, data)

    async def get_nutrition(self, stockcode: int) -> dict | None:
        return await self._get("nutrition_cache", "stockcode", stockcode, NUTRITION_TTL)

    async def set_nutrition(self, stockcode: int, data: dict) -> None:
        await self._set("nutrition_cache", "stockcode", stockcode, data)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
