# Release Notes

## v0.1.0

### What shipped
- Dual-mode server: OpenAPI + MCP on one process/port.
- Woolworths search/product/nutrition tools.
- SQLite cache with TTL, startup eviction, and hit/miss stats.
- CI with lint/tests and Sonar scan.
- Docker image build and GHCR publish workflow on `v*.*.*` tags.

### Operational notes
- `openai/gpt-oss-*` via vLLM requires non-streaming tool calls in Open WebUI.
- Nutrition coverage is best-effort based on upstream product metadata completeness.

### Known limitations
- No provider failover yet (Woolworths-only at present).
- Cache is local SQLite; horizontal scaling needs shared storage or external cache.
