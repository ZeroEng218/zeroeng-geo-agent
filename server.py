"""
server.py

Two surfaces, two trust models, one FastAPI app:

    GET  /health              -> liveness check, no auth
    POST /locate-state        -> ZeroEng's own backend only, gated by X-API-Key
    POST /register            -> public, anyone gets a free API key instantly
    /mcp/*                    -> public MCP server (streamable-http), gated by
                                  the API keys /register hands out

/locate-state auth: every request must include a header
    X-API-Key: <GEO_API_KEY>
matching the GEO_API_KEY environment variable set on this service. This is a
server-to-server secret -- it should be called from your website's own
backend, never embedded in browser-side JavaScript (anything shipped to a
browser is visible to anyone who opens dev tools).

/register + /mcp are the connective piece for agents that just visit
zeroeng.io: they have no way to know a shared secret, so instead they
register for their own key and use it as a Bearer token on MCP calls. See
api_keys.py and mcp_tools.py for the implementation.

Run locally:
    export ANTHROPIC_API_KEY=sk-ant-...
    export GEO_API_KEY=some-secret-you-pick
    export SUPABASE_URL=https://xxxx.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=...
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from geo_agent import locate_state
from api_keys import create_api_key
from mcp_tools import mcp_app

GEO_API_KEY = os.environ.get("GEO_API_KEY")

# The MCP app's lifespan MUST be threaded into FastAPI's, or its session
# manager never initializes and every /mcp request fails.
app = FastAPI(title="ZeroEng Geo Lookup Service", lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)


class CoordinateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/locate-state")
async def locate_state_endpoint(
    body: CoordinateRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    if not GEO_API_KEY:
        # Fail closed: an unset secret should never mean "open to everyone".
        raise HTTPException(
            status_code=500,
            detail="Service misconfigured: GEO_API_KEY is not set on the server.",
        )
    if x_api_key != GEO_API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")

    result = await locate_state(body.latitude, body.longitude)
    return result


@app.post("/register")
async def register(body: RegisterRequest):
    """Public, unauthenticated: anyone (human or agent) gets a live API key
    for the /mcp endpoint immediately. The key is shown here once -- it is
    never retrievable again, only revocable."""
    api_key = await create_api_key(body.name, body.email)
    return {
        "api_key": api_key,
        "notice": "Save this now -- it will not be shown again. "
        "Use it as 'Authorization: Bearer <api_key>' when calling /mcp.",
    }
