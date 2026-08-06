"""
mcp_tools.py

The public surface: any AI agent that finds this endpoint can call it
directly, no relationship with ZeroEng required beyond a free /register call.
This is deliberately a different trust model from server.py's /locate-state,
which is gated by a single shared GEO_API_KEY only ZeroEng's own backend
holds -- that secret can't be handed to an arbitrary visiting agent, so it
isn't used here.

Exposes one tool over streamable-http MCP (see https://mcp.zeroeng.io/mcp
once deployed): get_state_for_coordinates, calling geo_agent's
_lookup_state() directly. Unlike server.py's /locate-state, this does NOT
run its own Claude agent loop -- the caller is already an agent; it does its
own orchestration. This server just executes the deterministic lookup.

Auth: bearer tokens issued by POST /register (see api_keys.py), checked via
IssuedKeyVerifier against the Supabase-backed api_keys table.
"""

from fastmcp import FastMCP
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

from api_keys import verify_api_key
from geo_agent import _lookup_state


class IssuedKeyVerifier(TokenVerifier):
    """Validates bearer tokens against api_keys.verify_api_key (Supabase-backed)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not await verify_api_key(token):
            return None
        return AccessToken(token=token, client_id="zeroeng-registered-agent", scopes=[])


mcp = FastMCP(
    name="zeroeng-geo",
    instructions=(
        "Zero Engineering's geo lookup tools for the built environment. "
        "Get a free API key first via POST /register on this same host, "
        "then send it as 'Authorization: Bearer <key>' on MCP requests."
    ),
    auth=IssuedKeyVerifier(),
)


@mcp.tool
async def get_state_for_coordinates(latitude: float, longitude: float) -> dict:
    """Look up the U.S. state (and county) that a latitude/longitude point falls
    within, using the FCC/Census Bureau's authoritative boundary data.

    Args:
        latitude: Latitude in decimal degrees (WGS84), -90 to 90.
        longitude: Longitude in decimal degrees (WGS84), -180 to 180.

    Returns one of:
        {"status": "found", "state_name": ..., "state_code": ..., "county_name": ..., "state_fips": ...}
        {"status": "outside_us"}
        {"status": "error", "message": ...}
    """
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return {"status": "error", "message": "latitude/longitude out of valid range"}
    return await _lookup_state(latitude, longitude)


mcp_app = mcp.http_app(path="/", stateless_http=True, allowed_origins=["*"])
