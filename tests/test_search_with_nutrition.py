import pytest

import main


@pytest.mark.asyncio
async def test_search_with_nutrition_returns_available_items_when_limit_exceeds_results(monkeypatch):
    async def fake_search(query: str, page: int = 1):
        return {
            "search_term": query,
            "total_results": 2,
            "page": page,
            "products": [
                {
                    "stockcode": 1,
                    "name": "A",
                    "brand": "B",
                    "price": 1.0,
                    "package_size": "100g",
                    "is_available": True,
                },
                {
                    "stockcode": 2,
                    "name": "C",
                    "brand": "D",
                    "price": 2.0,
                    "package_size": "200g",
                    "is_available": True,
                },
            ],
        }

    async def fake_nutrition(stockcode: int):
        return {
            "nutrition": {"Sodium Quantity Per 100g - Total - NIP": f"{stockcode * 100}mg"},
            "ingredients": "Milk",
            "allergystatement": "Contains milk",
            "healthstarrating": "4",
        }

    monkeypatch.setattr(main, "_search", fake_search)
    monkeypatch.setattr(main, "_nutrition", fake_nutrition)

    result = await main._search_with_nutrition("cottage cheese", page=1, limit=12)

    assert result["search_term"] == "cottage cheese"
    assert result["total_results"] == 2
    assert len(result["nutrition_results"]) == 2
    assert result["nutrition_results"][0]["nutrition"]["Sodium Quantity Per 100g - Total - NIP"] == "100mg"
    assert result["nutrition_results"][1]["nutrition"]["Sodium Quantity Per 100g - Total - NIP"] == "200mg"


@pytest.mark.asyncio
async def test_search_with_nutrition_preserves_error_when_nutrition_fails(monkeypatch):
    async def fake_search(query: str, page: int = 1):
        return {
            "search_term": query,
            "total_results": 1,
            "page": page,
            "products": [
                {
                    "stockcode": 10,
                    "name": "Only Product",
                    "brand": "Brand",
                    "price": 3.5,
                    "package_size": "300g",
                    "is_available": True,
                }
            ],
        }

    async def fake_nutrition(_stockcode: int):
        return {"error": "upstream timeout"}

    monkeypatch.setattr(main, "_search", fake_search)
    monkeypatch.setattr(main, "_nutrition", fake_nutrition)

    result = await main._search_with_nutrition("cottage cheese", page=1, limit=5)

    assert len(result["nutrition_results"]) == 1
    item = result["nutrition_results"][0]
    assert item["nutrition"] is None
    assert item["nutrition_error"] == "upstream timeout"
