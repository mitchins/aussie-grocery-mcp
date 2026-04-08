"""SQLite cache with per-table TTLs for Woolworths data."""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

SEARCH_TTL = 7200          # 2 hours
PRODUCT_TTL = 7200         # 2 hours
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

_TABLE_TTLS = [
    ("search_cache", SEARCH_TTL),
    ("product_cache", PRODUCT_TTL),
    ("nutrition_cache", NUTRITION_TTL),
]


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total": self.total,
            "hit_rate": round(self.hit_rate, 3),
        }


class Cache:
    def __init__(self, db_path: str = "cache.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._stats: dict[str, CacheStats] = {
            "search": CacheStats(),
            "product": CacheStats(),
            "nutrition": CacheStats(),
        }

    async def _get_db(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self.db_path)
            await self._db.executescript(_INIT_SQL)
        return self._db

    # ── generic helpers ───────────────────────────────────────────────

    async def _get(self, table: str, key_col: str, key_val: Any, ttl: float, stat: str) -> dict | None:
        db = await self._get_db()
        sql = f"SELECT data_json, cached_at FROM {table} WHERE {key_col} = ?"
        async with db.execute(sql, (key_val,)) as cur:
            row = await cur.fetchone()
        if row and (time.time() - row[1]) < ttl:
            self._stats[stat].hits += 1
            return json.loads(row[0])
        self._stats[stat].misses += 1
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
        return await self._get("search_cache", "key", key, SEARCH_TTL, "search")

    async def set_search(self, key: str, data: dict) -> None:
        await self._set("search_cache", "key", key, data)

    async def get_product(self, stockcode: int) -> dict | None:
        return await self._get("product_cache", "stockcode", stockcode, PRODUCT_TTL, "product")

    async def set_product(self, stockcode: int, data: dict) -> None:
        await self._set("product_cache", "stockcode", stockcode, data)

    async def get_nutrition(self, stockcode: int) -> dict | None:
        return await self._get("nutrition_cache", "stockcode", stockcode, NUTRITION_TTL, "nutrition")

    async def set_nutrition(self, stockcode: int, data: dict) -> None:
        await self._set("nutrition_cache", "stockcode", stockcode, data)

    # ── observability ─────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return hit/miss counts and hit rate per cache table."""
        return {name: s.to_dict() for name, s in self._stats.items()}

    # ── maintenance ───────────────────────────────────────────────────

    async def evict_expired(self) -> dict[str, int]:
        """Delete rows older than their TTL. Returns row count removed per table."""
        db = await self._get_db()
        now = time.time()
        counts: dict[str, int] = {}
        for table, ttl in _TABLE_TTLS:
            cur = await db.execute(f"DELETE FROM {table} WHERE cached_at < ?", (now - ttl,))
            counts[table] = cur.rowcount
        await db.commit()
        total = sum(counts.values())
        if total:
            logger.info("evict_expired: removed %d stale rows %s", total, counts)
        return counts

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
