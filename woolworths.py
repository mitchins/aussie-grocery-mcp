"""Woolworths API client — reverse-engineered from woolworths.com.au."""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.woolworths.com.au"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:148.0) "
        "Gecko/20100101 Firefox/148.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# Session cookie lifetime (~1 h), refresh early at 50 min
_SESSION_TTL = 3000


class WoolworthsClient:
    """Async client that maintains a cookie-based session with woolworths.com.au."""

    def __init__(self, store_id: int = 1104):
        self.store_id = store_id
        self._client: httpx.AsyncClient | None = None
        self._session_expires: float = 0

    async def _ensure_session(self) -> httpx.AsyncClient:
        now = time.time()
        if self._client is None or now >= self._session_expires:
            if self._client:
                await self._client.aclose()
            self._client = httpx.AsyncClient(
                headers=_HEADERS,
                follow_redirects=True,
                timeout=30.0,
            )
            # Hit homepage to pick up session cookies (w-rctx, etc.)
            await self._client.get(BASE_URL)
            self._session_expires = now + _SESSION_TTL
            logger.info("Woolworths session initialised")
        return self._client

    # ── Search ────────────────────────────────────────────────────────

    async def search_products(
        self,
        search_term: str,
        page: int = 1,
        page_size: int = 36,
    ) -> dict[str, Any]:
        client = await self._ensure_session()
        payload = {
            "Filters": [],
            "IsSpecial": False,
            "Location": f"/shop/search/products?searchTerm={search_term}",
            "PageNumber": page,
            "PageSize": page_size,
            "SearchTerm": search_term,
            "SortType": "TraderRelevance",
            "IsHideEverydayMarketProducts": False,
            "IsRegisteredRewardCardPromotion": None,
            "ExcludeSearchTypes": ["UntraceableVendors"],
            "GpBoost": 0,
            "GroupEdmVariants": False,
            "EnableAdReRanking": False,
        }
        resp = await client.post(
            f"{BASE_URL}/apis/ui/Search/products",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Product detail ────────────────────────────────────────────────

    async def get_product_detail(self, stockcode: int) -> dict[str, Any]:
        client = await self._ensure_session()
        resp = await client.get(
            f"{BASE_URL}/apis/ui/product/detail/{stockcode}",
            params={"isMobile": "false", "useVariant": "true"},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        # The detail endpoint may nest inside a "Product" key
        if "Product" in data and isinstance(data["Product"], dict):
            return data["Product"]
        return data

    # ── Batch products by stockcode ───────────────────────────────────

    async def get_products(self, stockcodes: list[int]) -> list[dict[str, Any]]:
        client = await self._ensure_session()
        codes = ",".join(str(s) for s in stockcodes)
        resp = await client.get(f"{BASE_URL}/apis/ui/products/{codes}")
        resp.raise_for_status()
        return resp.json()

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
