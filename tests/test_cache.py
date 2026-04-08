import pytest

import cache as cache_module
from cache import Cache


@pytest.mark.asyncio
async def test_search_cache_hit(tmp_path):
    db_path = tmp_path / "cache_test.db"
    c = Cache(str(db_path))

    payload = {"search_term": "cottage cheese", "products": []}
    await c.set_search("cottage cheese|1", payload)

    result = await c.get_search("cottage cheese|1")
    assert result == payload

    await c.close()


@pytest.mark.asyncio
async def test_search_cache_expires_with_ttl(tmp_path, monkeypatch):
    db_path = tmp_path / "cache_test_expiry.db"
    c = Cache(str(db_path))

    fake_now = [1_000.0]

    def _fake_time():
        return fake_now[0]

    monkeypatch.setattr(cache_module.time, "time", _fake_time)

    await c.set_search("tim tams|1", {"ok": True})
    assert await c.get_search("tim tams|1") == {"ok": True}

    fake_now[0] += cache_module.SEARCH_TTL + 1
    assert await c.get_search("tim tams|1") is None

    await c.close()
