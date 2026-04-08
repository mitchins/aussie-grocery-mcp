# aussie-grocery-mcp

Dual-mode server for checking Woolworths Australia grocery prices, product details, and nutrition information.

- OpenAPI endpoints for Open WebUI Tool Servers
- MCP Streamable HTTP endpoint for MCP clients (for example Claude Desktop)

## Tools

| Tool | Description |
|------|-------------|
| `search_products(query, page)` | Search the Woolworths catalogue by keyword |
| `get_product(stockcode)` | Full product detail — description, ingredients, pricing |
| `get_nutrition(stockcode)` | Nutrition panel, allergens, health star rating |

## Quick Start

```bash
# Clone & run (uv)
cd aussie-grocery-mcp
uv sync

# Configure (optional — defaults to Chullora store)
cp .env.example .env

# Run
uv run python main.py
```

Prefer pip? See the development guide.

Server starts on `http://0.0.0.0:8765` and exposes:

- OpenAPI schema: `http://localhost:8765/openapi.json`
- Swagger docs: `http://localhost:8765/docs`
- MCP Streamable HTTP: `http://localhost:8765/mcp/`

## Open WebUI Setup

### 1. Register the Tool Server

1. Go to **Admin → Settings → Integrations → Manage Tool Servers → Add**
2. Add the OpenAPI server URL:
   - Local Open WebUI: `http://localhost:8765`
   - Docker Open WebUI: `http://host.docker.internal:8765`
3. Open WebUI will read `openapi.json` and import all tools.

### 2. Enable Native Tool Calling (Required for Agentic Use)

Tool calls only work correctly when the model is set to **Native** function calling mode. Without this, the model may echo tool XML tags instead of executing them.

**Global / per-model (recommended):**
1. **Admin Panel → Settings → Models**
2. Select your model → **Advanced Parameters**
3. Set **Function Calling** → **Native**

**Per-chat (quick test):**
1. Inside a chat, click the **⚙️ Chat Controls** icon
2. **Advanced Params → Function Calling → Native**

### 3. Model-Specific Notes

| Model family | Tool calling | Notes |
|---|---|---|
| Qwen (any) | ✅ Works out of the box | Streaming on, no special config needed |
| `openai/gpt-oss-20b` | ✅ Works with config below | See vLLM flags; **disable streaming** in Open WebUI model settings |
| `openai/gpt-oss-120b` | ✅ Same as 20b | |

#### gpt-oss on vLLM

Requires two extra flags when serving:

```bash
vllm serve openai/gpt-oss-20b \
  --tool-call-parser openai \
  --enable-auto-tool-choice \
  ...other flags...
```

Then in Open WebUI model settings for this model:
- **Function Calling:** Native
- **Stream Chat Response:** Off  ← critical; streaming tool-call chunks crash with gpt-oss on vLLM
- **Parallel Tool Calls:** Off

> Non-streaming tool calls work correctly through vLLM. The streaming path has a known `list index out of range` crash in the tool-call chunk assembler. Start a **brand-new chat** after changing these settings — malformed tool history from previous turns can persist and break the loop.

## MCP Client Setup

Use this URL for MCP-capable clients:

- `http://localhost:8765/mcp/`

## Docker

```bash
docker build -t aussie-grocery-mcp .
docker run -p 8765:8765 aussie-grocery-mcp
```

## Development

Contributor workflows (pip install, testing/linting, CI/CD, Sonar, and GHCR release) are in [development.md](development.md).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WOOLWORTHS_STORE_ID` | `1104` | Woolworths store ID (Chullora) |
| `CACHE_DB_PATH` | `cache.db` | SQLite cache file path |
| `PORT` | `8765` | Server port |
| `HOST` | `0.0.0.0` | Bind address |

## Caching

- **Search results:** 2-hour TTL
- **Product details:** 2-hour TTL
- **Nutrition data:** 30-day TTL

All cached in a local SQLite database.
