"""
Aussie Grocery — combined MCP + OpenAPI server for Woolworths price checking.

Transports served on one port:
  GET  /search_products?query=...   OpenAPI endpoint  (Open WebUI Tool Servers)
  GET  /product/{stockcode}         OpenAPI endpoint
  GET  /nutrition/{stockcode}       OpenAPI endpoint
  GET  /openapi.json                Auto-generated OpenAPI schema
  GET  /docs                        Swagger UI
  /mcp                              FastMCP Streamable HTTP  (Claude Desktop etc.)

Run:
    python main.py          # all transports on PORT (default 8765)
"""

import asyncio
import json
import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from cache import Cache
from woolworths import WoolworthsClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

STORE_ID = int(os.getenv("WOOLWORTHS_STORE_ID", "1104"))
CACHE_DB = os.getenv("CACHE_DB_PATH", "cache.db")
PORT = int(os.getenv("PORT", "8765"))
HOST = os.getenv("HOST", "0.0.0.0")

# ── Singletons ────────────────────────────────────────────────────────

api = WoolworthsClient(store_id=STORE_ID)
cache = Cache(db_path=CACHE_DB)


class SearchProductsRequest(BaseModel):
    query: str = Field(
        ...,
        description="Search term, for example 'cottage cheese' or 'tim tams'",
    )
    page: int = Field(1, ge=1, description="Results page, default 1")


class StockcodeRequest(BaseModel):
    stockcode: int = Field(..., description="Woolworths stockcode, for example 41402")


class SearchProductsWithNutritionRequest(BaseModel):
    query: str = Field(
        ...,
        description="Search term, for example 'cottage cheese'",
    )
    page: int = Field(1, ge=1, description="Search results page, default 1")
    limit: int = Field(
        5,
        ge=1,
        description="Number of matching products to enrich with nutrition (capped at one page of results)",
    )


# ── Helpers ───────────────────────────────────────────────────────────


def _fmt_product(p: dict) -> dict:
    """Flatten a raw Woolworths product object into the fields an LLM cares about."""
    stockcode = p.get("Stockcode")
    url_name = p.get("UrlFriendlyName", "")
    return {
        "stockcode": stockcode,
        "name": p.get("Name") or p.get("DisplayName"),
        "brand": p.get("Brand"),
        "price": p.get("Price"),
        "was_price": p.get("WasPrice"),
        "cup_price": p.get("CupPrice"),
        "cup_string": p.get("CupString"),
        "is_on_special": p.get("IsOnSpecial", False),
        "savings_amount": p.get("SavingsAmount"),
        "is_available": p.get("IsAvailable", False),
        "package_size": p.get("PackageSize"),
        "image": p.get("MediumImageFile"),
        "url": (
            f"https://www.woolworths.com.au/shop/productdetails/{stockcode}/{url_name}"
            if stockcode
            else None
        ),
    }


def _parse_nutrition(detail: dict) -> dict | None:
    """Pull the nutrition panel out of a product-detail response."""
    attrs = detail.get("AdditionalAttributes") or {}
    raw = attrs.get("nutritionalinformation")
    if not raw:
        return None

    try:
        nutrition = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None

    result: dict = {
        "product_name": detail.get("Name"),
        "stockcode": detail.get("Stockcode"),
    }

    if isinstance(nutrition, dict):
        items = nutrition.get("Attributes", [])
        result["nutrition"] = {a["Name"]: a.get("Value") for a in items if a.get("Name")}
    elif isinstance(nutrition, list):
        result["nutrition"] = nutrition
    else:
        result["nutrition_raw"] = str(nutrition)

    for key in (
        "ingredients",
        "allergystatement",
        "lifestyleanddietarystatement",
        "healthstarrating",
    ):
        val = attrs.get(key)
        if val:
            result[key] = val

    return result


# ── Core logic (shared by MCP + OpenAPI) ──────────────────────────────


async def _search(query: str, page: int = 1) -> dict:
    cache_key = f"{query.lower().strip()}|{page}"
    hit = await cache.get_search(cache_key)
    if hit:
        logger.info("search cache hit: %s", cache_key)
        return hit
    raw = await api.search_products(query, page=page)
    products = [
        _fmt_product(p)
        for group in raw.get("Products", [])
        for p in group.get("Products", [])
    ]
    result = {
        "search_term": raw.get("CorrectSearchTerm") or query,
        "total_results": raw.get("SearchResultsCount", 0),
        "page": page,
        "products": products,
    }
    await cache.set_search(cache_key, result)
    return result


async def _product(stockcode: int) -> dict:
    hit = await cache.get_product(stockcode)
    if hit:
        logger.info("product cache hit: %d", stockcode)
        return hit
    raw = await api.get_product_detail(stockcode)
    attrs = raw.get("AdditionalAttributes") or {}
    result = _fmt_product(raw)
    result.update(
        {
            "description": attrs.get("description"),
            "ingredients": attrs.get("ingredients"),
            "allergens": attrs.get("allergystatement"),
            "dietary_info": attrs.get("lifestyleanddietarystatement"),
            "health_star_rating": attrs.get("healthstarrating"),
            "category": attrs.get("sapcategoryname"),
            "barcode": raw.get("Barcode"),
        }
    )
    await cache.set_product(stockcode, result)
    return result


async def _nutrition(stockcode: int) -> dict:
    hit = await cache.get_nutrition(stockcode)
    if hit:
        logger.info("nutrition cache hit: %d", stockcode)
        return hit
    raw = await api.get_product_detail(stockcode)
    result = _parse_nutrition(raw)
    if result is None:
        return {"error": f"No nutrition info available for stockcode {stockcode}"}
    await cache.set_nutrition(stockcode, result)
    return result


async def _search_with_nutrition(query: str, page: int = 1, limit: int = 5) -> dict:
    search_result = await _search(query, page)
    selected_products = search_result.get("products", [])[:limit]
    nutritions = await asyncio.gather(
        *(_nutrition(product["stockcode"]) for product in selected_products),
        return_exceptions=True,
    )

    products_with_nutrition = []
    for product, nutrition in zip(selected_products, nutritions, strict=False):
        nutrition_payload = nutrition
        if isinstance(nutrition, Exception):
            nutrition_payload = {"error": str(nutrition)}

        products_with_nutrition.append(
            {
                "stockcode": product.get("stockcode"),
                "name": product.get("name"),
                "brand": product.get("brand"),
                "price": product.get("price"),
                "package_size": product.get("package_size"),
                "is_available": product.get("is_available"),
                "nutrition": nutrition_payload.get("nutrition")
                if isinstance(nutrition_payload, dict)
                else None,
                "ingredients": nutrition_payload.get("ingredients")
                if isinstance(nutrition_payload, dict)
                else None,
                "allergens": nutrition_payload.get("allergystatement")
                if isinstance(nutrition_payload, dict)
                else None,
                "health_star_rating": nutrition_payload.get("healthstarrating")
                if isinstance(nutrition_payload, dict)
                else None,
                "nutrition_error": nutrition_payload.get("error")
                if isinstance(nutrition_payload, dict)
                else str(nutrition_payload),
            }
        )

    return {
        "search_term": search_result.get("search_term"),
        "total_results": search_result.get("total_results"),
        "page": search_result.get("page"),
        "nutrition_results": products_with_nutrition,
    }


# ── MCP server  (Claude Desktop, any MCP client → /mcp) ──────────────

mcp = FastMCP(
    "Woolworths Grocery",
    instructions=(
        "You help users find grocery products and prices at Woolworths Australia. "
        "Use search_products to find items, get_product for full details, "
        "and get_nutrition for nutritional information."
    ),
)


@mcp.tool()
async def search_products(query: str, page: int = 1) -> str:
    """Search Woolworths for grocery products by name or keyword.

    Returns product names, current prices, specials, and availability
    for the configured store.

    Args:
        query: Search term, e.g. "cottage cheese", "tim tams", "chicken breast".
        page: Results page (36 items per page). Default 1.
    """
    return json.dumps(await _search(query, page), indent=2)


@mcp.tool()
async def get_product(stockcode: int) -> str:
    """Get full details for a Woolworths product by its stockcode.

    Includes description, ingredients, pricing, and availability.
    Use search_products first to discover stockcodes.

    Args:
        stockcode: Woolworths numeric product code, e.g. 41402.
    """
    return json.dumps(await _product(stockcode), indent=2)


@mcp.tool()
async def get_nutrition(stockcode: int) -> str:
    """Get the nutrition panel for a Woolworths product.

    Returns per-serve and per-100 g values, ingredients, allergens,
    dietary info, and health star rating when available.

    Args:
        stockcode: Woolworths numeric product code, e.g. 41402.
    """
    return json.dumps(await _nutrition(stockcode), indent=2)


# ── OpenAPI server  (Open WebUI Tool Servers → /) ────────────────────

mcp_http_app = mcp.http_app(transport="streamable-http", path="/")

app = FastAPI(
    title="Woolworths Grocery",
    description=(
        "Search Woolworths Australia for grocery products, prices, and nutrition info. "
        "Call search_products first to discover stockcodes, then use get_product or "
        "get_nutrition for detail."
    ),
    version="1.0.0",
    lifespan=mcp_http_app.lifespan,
)


@app.get(
    "/search_products",
    summary="Search Woolworths grocery catalogue",
    operation_id="search_products",
    description=(
        "Search Woolworths products by keyword. Use this first when you need stockcodes. "
        "If the user asks for nutrition across matching products, prefer search_products_with_nutrition."
    ),
    include_in_schema=False,
)
async def api_search(
    query: str = Query(..., description="Search term, e.g. 'cottage cheese'"),
    page: int = Query(1, ge=1, description="Results page (36 items per page)"),
):
    return await _search(query, page)


@app.post(
    "/search_products",
    summary="Search Woolworths grocery catalogue",
    operation_id="search_products",
    description=(
        "Search Woolworths products by keyword. Use this first when you need stockcodes. "
        "If the user asks for nutrition across matching products, prefer search_products_with_nutrition."
    ),
)
async def api_search_post(request: SearchProductsRequest):
    return await _search(request.query, request.page)


@app.get(
    "/product/{stockcode}",
    summary="Get full product detail by stockcode",
    operation_id="get_product",
    description="Get detailed product information for a known Woolworths stockcode.",
    include_in_schema=False,
)
async def api_product(stockcode: int):
    return await _product(stockcode)


@app.post(
    "/get_product",
    summary="Get full product detail by stockcode",
    operation_id="get_product",
    description="Get detailed product information for a known Woolworths stockcode.",
)
async def api_product_post(request: StockcodeRequest):
    return await _product(request.stockcode)


@app.get(
    "/nutrition/{stockcode}",
    summary="Get nutrition panel by stockcode",
    operation_id="get_nutrition",
    description=(
        "Get nutrition, ingredients, dietary info, and health star rating for a known stockcode. "
        "Use search_products first if you do not know the stockcode."
    ),
    include_in_schema=False,
)
async def api_nutrition(stockcode: int):
    return await _nutrition(stockcode)


@app.post(
    "/get_nutrition",
    summary="Get nutrition panel by stockcode",
    operation_id="get_nutrition",
    description=(
        "Get nutrition, ingredients, dietary info, and health star rating for a known stockcode. "
        "Use search_products first if you do not know the stockcode."
    ),
)
async def api_nutrition_post(request: StockcodeRequest):
    return await _nutrition(request.stockcode)


@app.get(
    "/search_products_with_nutrition",
    summary="Search products and return nutrition for actual matching items",
    operation_id="search_products_with_nutrition",
    description=(
        "Best tool when the user asks for nutrition facts for a product family such as 'cottage cheese'. "
        "This searches real products, then fetches nutrition for the top matching items."
    ),
    include_in_schema=False,
)
async def api_search_with_nutrition(
    query: str = Query(..., description="Search term, e.g. 'cottage cheese'"),
    page: int = Query(1, ge=1, description="Search results page"),
    limit: int = Query(5, ge=1, description="Maximum number of matching products to enrich with nutrition"),
):
    return await _search_with_nutrition(query, page, limit)


@app.post(
    "/search_products_with_nutrition",
    summary="Search products and return nutrition for actual matching items",
    operation_id="search_products_with_nutrition",
    description=(
        "Best tool when the user asks for nutrition facts for a product family such as 'cottage cheese'. "
        "Call this directly with a query and optional limit. Returns real matching products with nutrition data included."
    ),
)
async def api_search_with_nutrition_post(request: SearchProductsWithNutritionRequest):
    return await _search_with_nutrition(request.query, request.page, request.limit)


# Mount MCP Streamable HTTP under /mcp.
app.mount("/mcp", mcp_http_app)


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting on %s:%d  —  OpenAPI: /docs  |  MCP: /mcp", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT)
