# ZeroEng Geo Lookup Service

Given a latitude/longitude, returns the U.S. state it falls within. First
operation in a pipeline that will grow to include more location-based
lookups for the built-environment work at Zero Engineering.

State determination is not left to the model's own geographic knowledge --
it calls the FCC/Census Bureau's authoritative Census Area API through a
custom tool, and Claude only orchestrates + formats the result. See
`geo_agent.py` for the full design notes.

## Endpoints

- `GET /health` -- liveness check, no auth required.
- `POST /locate-state` -- requires header `X-API-Key: <GEO_API_KEY>`.
  Body: `{"latitude": 30.2672, "longitude": -97.7431}`
  Response: `{"latitude": ..., "longitude": ..., "state": "Texas", "state_code": "TX", "county": "Travis County", "status": "found", "notes": "..."}`

## Environment variables

- `ANTHROPIC_API_KEY` -- required, used by the Claude Agent SDK.
- `GEO_API_KEY` -- required, a secret you choose. Callers must send it back
  as the `X-API-Key` header. Call this service from your own backend only --
  never from browser-side JavaScript, since anything sent to a browser can
  be read by anyone who opens dev tools.

## Local development

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
export GEO_API_KEY=some-secret-you-pick
uvicorn server:app --reload
```

## Adding the next operation

Add another `@tool`-decorated function to `geo_agent.py`, list it in
`allowed_tools`, and extend `OUTPUT_SCHEMA` with whatever new fields that
step needs. See the "Give Claude custom tools" doc this was built from:
https://code.claude.com/docs/en/agent-sdk/custom-tools
