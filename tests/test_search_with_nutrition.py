import asyncio

import pytest

import main
from cache import Cache


@pytest.mark.asyncio
async def test_search_with_nutrition_returns_available_items_when_limit_exceeds_results(monkeypatch):
    async def fake_search(query: str, page: int = 1):
        await asyncio.sleep(0)
        return {
            "search_term": query,
            "total_results": 2,
            "page": page,
            "products": [
                {"stockcode": 1, "name": "A", "brand": "B", "price": 1.0, "package_size": "100g", "is_available": True},
                {"stockcode": 2, "name": "C", "brand": "D", "price": 2.0, "package_size": "200g", "is_available": True},
            ],
        }

    async def fake_nutrition(stockcode: int):
        await asyncio.sleep(0)
        return {
            "nutrition": {"Sodium Quantity Per 100g - Total - NIP": f"{stockcode * 100}mg"},
            "ingredients": "Milk",
            "allergystatement": "Contains milk",
            "healthstarrating": "4",
        }

    monkeypatch.setattr(main, "_search", fake_search)
    monkeypatch.setattr(main, "_nutrition", fake_nutrition)

    result = await main._search_with_nutrition("cottage cheese", page=1, limit=12)

    assert result["total_results"] == 2
    assert len(result["nutrition_results"]) == 2
    assert result["nutrition_results"][0]["nutrition"]["Sodium Quantity Per 100g - Total - NIP"] == "100mg"
    assert result["nutrition_results"][1]["nutrition"]["Sodium Quantity Per 100g - Total - NIP"] == "200mg"


@pytest.mark.asyncio
async def test_search_with_nutrition_preserves_error_when_nutrition_fails(monkeypatch):
    async def fake_search(query: str, page: int = 1):
        await asyncio.sleep(0)
        return {
            "search_term": query,
            "total_results": 1,
            "page": page,
            "products": [
                {"stockcode": 10, "name": "Only Product", "brand": "Brand", "price": 3.5, "package_size": "300g", "is_available": True}
            ],
        }

    async def fake_nutrition(_stockcode: int):
        await asyncio.sleep(0)
        return {"error": "upstream timeout"}

    monkeypatch.setattr(main, "_search", fake_search)
    monkeypatch.setattr(main, "_nutrition", fake_nutrition)

    result = await main._search_with_nutrition("cottage cheese", page=1, limit=5)

    item = result["nutrition_results"][0]
    assert item["nutrition"] is None
    assert item["nutrition_error"] == "upstream timeout"


@pytest.mark.asyncio
async def test_nutrition_negative_result_is_cached(monkeypatch):
    """When a product has no nutrition data, the error dict is cached so we don't re-fetch."""
    call_count = 0

    async def fake_get_product_detail(_stockcode: int):
        await asyncio.sleep(0)
        nonlocal call_count
        call_count += 1
        return {"Name": "No Nutrition Product", "Stockcode": 99, "AdditionalAttributes": {}}

    tmp_cache = Cache(":memory:")
    monkeypatch.setattr(main, "cache", tmp_cache)
    monkeypatch.setattr(main.api, "get_product_detail", fake_get_product_detail)
    # Clear in-flight state between test runs
    main._nutrition_inflight.clear()

    result1 = await main._nutrition(99)
    result2 = await main._nutrition(99)

    assert result1 == result2
    assert "error" in result1
    # Second call should be served from cache — only one backend call
    assert call_count == 1
    await tmp_cache.close()

