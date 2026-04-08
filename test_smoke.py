"""Quick smoke test — calls each MCP tool once."""

import json
import sys

import httpx

BASE = "http://localhost:8765/mcp/"
HDRS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def call(session_id, method_id, method, params=None):
    h = {**HDRS, "Mcp-Session-Id": session_id}
    r = httpx.post(
        BASE,
        headers=h,
        timeout=30,
        follow_redirects=True,
        json={"jsonrpc": "2.0", "id": method_id, "method": method, "params": params or {}},
    )
    for line in r.text.split("\n"):
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return None


def main():
    # 1) Initialize
    r = httpx.post(
        BASE,
        headers=HDRS,
        follow_redirects=True,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        },
    )
    sid = r.headers["mcp-session-id"]
    print(f"Session: {sid}\n")

    # 2) List tools
    resp = call(sid, 2, "tools/list")
    if resp is None:
        print("ERROR: tools/list returned no response data")
        sys.exit(1)
    tools = resp["result"]["tools"]
    print("Tools:")
    for t in tools:
        print(f"  - {t['name']}")
    print()

    # 3) search_products
    print("=== search_products('cottage cheese') ===")
    resp = call(sid, 3, "tools/call", {"name": "search_products", "arguments": {"query": "cottage cheese"}})
    if resp is None:
        print("ERROR: search_products returned no response data")
        sys.exit(1)
    if "error" in resp:
        print("ERROR:", resp["error"])
        sys.exit(1)
    data = json.loads(resp["result"]["content"][0]["text"])
    print(f"  Results: {data['total_results']}")
    for p in data["products"][:5]:
        tag = " [SPECIAL]" if p.get("is_on_special") else ""
        print(f"  ${p['price']:.2f} - {p['name']}{tag}")

    if not data["products"]:
        print("  (no products returned)")
        sys.exit(0)

    # 4) get_product on first result
    first = data["products"][0]["stockcode"]
    print(f"\n=== get_product({first}) ===")
    resp = call(sid, 4, "tools/call", {"name": "get_product", "arguments": {"stockcode": first}})
    if resp is None:
        print("ERROR: get_product returned no response data")
        sys.exit(1)
    if "error" in resp:
        print("ERROR:", resp["error"])
    else:
        detail = json.loads(resp["result"]["content"][0]["text"])
        print(f"  {detail.get('name')} — ${detail.get('price')}")
        print(f"  Brand: {detail.get('brand')}")
        print(f"  Description: {(detail.get('description') or '')[:120]}...")

    # 5) get_nutrition on first result
    print(f"\n=== get_nutrition({first}) ===")
    resp = call(sid, 5, "tools/call", {"name": "get_nutrition", "arguments": {"stockcode": first}})
    if resp is None:
        print("ERROR: get_nutrition returned no response data")
        sys.exit(1)
    if "error" in resp:
        print("ERROR:", resp["error"])
    else:
        nutr = json.loads(resp["result"]["content"][0]["text"])
        if "error" in nutr:
            print(f"  {nutr['error']}")
        else:
            print(f"  Product: {nutr.get('product_name')}")
            panels = nutr.get("nutrition", {})
            if isinstance(panels, dict):
                for k, v in list(panels.items())[:8]:
                    print(f"  {k}: {v}")
            print(f"  Ingredients: {(nutr.get('ingredients') or '')[:120]}...")

    print("\n✅ All tests passed")


if __name__ == "__main__":
    main()
