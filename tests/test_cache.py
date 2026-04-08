import pytest

import cache as cache_module
from cache import Cache


@pytest.mark.asyncio
async def test_search_cache_hit(tmp_path):
    c = Cache(str(tmp_path / "cache_test.db"))
    payload = {"search_term": "cottage cheese", "products": []}
    await c.set_search("cottage cheese|1", payload)
    assert await c.get_search("cottage cheese|1") == payload
    await c.close()


@pytest.mark.asyncio
async def test_search_cache_expires_with_ttl(tmp_path, monkeypatch):
    c = Cache(str(tmp_path / "cache_expiry.db"))
    fake_now = [1_000.0]
    monkeypatch.setattr(cache_module.time, "time", lambda: fake_now[0])

    await c.set_search("tim tams|1", {"ok": True})
    assert await c.get_search("tim tams|1") == {"ok": True}

    fake_now[0] += cache_module.SEARCH_TTL + 1
    assert await c.get_search("tim tams|1") is None
    await c.close()


@pytest.mark.asyncio
async def test_cache_stats_track_hits_and_misses(tmp_path):
    c = Cache(str(tmp_path / "stats.db"))

    # Two misses, then one hit
    await c.get_search("a|1")
    await c.get_search("b|1")
    await c.set_search("a|1", {"x": 1})
    await c.get_search("a|1")

    s = c.stats()
    assert s["search"]["hits"] == 1
    assert s["search"]["misses"] == 2
    assert s["search"]["total"] == 3
    assert s["search"]["hit_rate"] == pytest.approx(1 / 3, abs=0.001)
    await c.close()


@pytest.mark.asyncio
async def test_evict_expired_removes_stale_rows(tmp_path, monkeypatch):
    c = Cache(str(tmp_path / "evict.db"))
    fake_now = [1_000.0]
    monkeypatch.setattr(cache_module.time, "time", lambda: fake_now[0])

    await c.set_search("stale|1", {"old": True})
    await c.set_product(999, {"old": True})

    # Advance time past SEARCH_TTL and PRODUCT_TTL
    fake_now[0] += cache_module.SEARCH_TTL + 1

    counts = await c.evict_expired()
    assert counts["search_cache"] == 1
    assert counts["product_cache"] == 1
    assert counts["nutrition_cache"] == 0
    await c.close()

