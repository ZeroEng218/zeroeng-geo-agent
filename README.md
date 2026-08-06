# ZeroEng Geo Lookup Service

Given a latitude/longitude, returns the U.S. state it falls within. First
operation in a pipeline that will grow to include more location-based
lookups for the built-environment work at Zero Engineering.

State determination is not left to the model's own geographic knowledge --
it calls the FCC/Census Bureau's authoritative Census Area API through a
custom tool. See `geo_agent.py` for the full design notes.

There are two ways to call it, for two different audiences:

- **`/locate-state`** -- ZeroEng's own backend only, gated by a shared
  secret. Runs the lookup through a Claude agent that orchestrates the tool
  call and formats a fixed-schema response.
- **`/mcp`** -- any AI agent on the internet, no relationship with ZeroEng
  required beyond a free, instant `/register` call. This is the connective
  piece for agents that just visit zeroeng.io and want to call a tool
  directly -- they self-serve a key rather than needing a secret only our
  backend could hold. See `mcp_tools.py` and `api_keys.py`.

## Endpoints

- `GET /health` -- liveness check, no auth required.
- `POST /locate-state` -- requires header `X-API-Key: <GEO_API_KEY>`.
  Body: `{"latitude": 30.2672, "longitude": -97.7431}`
  Response: `{"latitude": ..., "longitude": ..., "state": "Texas", "state_code": "TX", "county": "Travis County", "status": "found", "notes": "..."}`
- `POST /register` -- public, no auth. Body: `{"name": "...", "email": "..."}`.
  Response: `{"api_key": "zg_live_...", "notice": "..."}`. The key is shown
  once, never retrievable again -- store it like any other secret.
- `/mcp` -- streamable-http MCP server. Requires header
  `Authorization: Bearer <api_key>` from `/register`. Exposes one tool so
  far: `get_state_for_coordinates(latitude, longitude)`.

### Calling `/mcp` as an agent

```bash
# 1. Get a key
curl -X POST https://mcp.zeroeng.io/register \
  -H "Content-Type: application/json" \
  -d '{"name": "My Agent", "email": "me@example.com"}'

# 2. Connect any MCP client to https://mcp.zeroeng.io/mcp with
#    Authorization: Bearer <api_key>, then call get_state_for_coordinates.
```

## Environment variables

- `ANTHROPIC_API_KEY` -- required, used by the Claude Agent SDK (for
  `/locate-state`'s internal agent run).
- `GEO_API_KEY` -- required, a secret you choose. Callers must send it back
  as the `X-API-Key` header on `/locate-state`. Call that endpoint from your
  own backend only -- never from browser-side JavaScript, since anything
  sent to a browser can be read by anyone who opens dev tools. (`/mcp` and
  `/register` have a deliberately different, public trust model -- see
  above.)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` -- required, back the
  `api_keys` table that `/register`/`/mcp` auth against. The service-role
  key is a server-side secret; never expose it to callers.

## Local development

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export GEO_API_KEY=some-secret-you-pick
export SUPABASE_URL=https://xxxx.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=...
uvicorn server:app --reload
```

## Adding the next operation

Add another `@tool`-decorated function to `geo_agent.py` for the
`/locate-state` path (list it in `allowed_tools`, extend `OUTPUT_SCHEMA`).
See the "Give Claude custom tools" doc this was built from:
https://code.claude.com/docs/en/agent-sdk/custom-tools

To expose the same new operation to public agents via `/mcp`, add another
`@mcp.tool` function in `mcp_tools.py` calling the same underlying lookup.
