"""
server.py

Turns geo_agent.py's locate_state() into a small HTTP service:

    GET  /health              -> liveness check, no auth
    POST /locate-state        -> { "latitude": .., "longitude": .. } -> state lookup

Auth: every /locate-state request must include a header
    X-API-Key: <GEO_API_KEY>
matching the GEO_API_KEY environment variable set on this service. This is a
server-to-server secret -- it should be called from your website's own
backend, never embedded in browser-side JavaScript (anything shipped to a
browser is visible to anyone who opens dev tools).

Run locally:
    export ANTHROPIC_API_KEY=sk-ant-...
    export GEO_API_KEY=some-secret-you-pick
    uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from geo_agent import locate_state

app = FastAPI(title="ZeroEng Geo Lookup Service")

GEO_API_KEY = os.environ.get("GEO_API_KEY")


class CoordinateRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


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
