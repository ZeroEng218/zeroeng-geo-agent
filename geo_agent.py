"""
geo_agent.py

Step 1 of a production agent pipeline: given a latitude/longitude, reliably
determine which U.S. state that point falls within.

Design decisions (see conversation for rationale):
  - The state determination itself is NOT left to the model's geographic
    knowledge. It's delegated to a custom tool that calls the FCC's Census
    Area API (backed by U.S. Census Bureau TIGER/Line boundary data) -- a
    free, authoritative, no-API-key-required source. This avoids
    hallucination near state borders.
  - Claude's job is orchestration: call the tool, interpret edge cases
    (ocean, non-US, invalid input), and emit a response that matches a
    fixed JSON Schema every time (via the Agent SDK's `output_format`).
  - This is built as an Agent SDK tool + server so later steps (jurisdiction
    lookup, permitting rules, code requirements, etc.) can be added as
    additional tools on the same server without changing this contract.

Requires:
    pip install claude-agent-sdk httpx

Run:
    python geo_agent.py
"""

import asyncio
from typing import Any, Optional

import httpx

from claude_agent_sdk import (
    tool,
    create_sdk_mcp_server,
    query,
    ClaudeAgentOptions,
    ResultMessage,
)

FCC_AREA_API = "https://geo.fcc.gov/api/census/area"

# ---------------------------------------------------------------------------
# 1. The tool: a deterministic lookup, not a model guess.
# ---------------------------------------------------------------------------

TOOL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "latitude": {
            "type": "number",
            "minimum": -90,
            "maximum": 90,
            "description": "Latitude in decimal degrees (WGS84).",
        },
        "longitude": {
            "type": "number",
            "minimum": -180,
            "maximum": 180,
            "description": "Longitude in decimal degrees (WGS84).",
        },
    },
    "required": ["latitude", "longitude"],
}


# Pulled out from the @tool handler on purpose: this is the part with real
# logic (the HTTP call + response parsing), so it's the part worth unit
# testing directly without spinning up the SDK/agent machinery. See
# test_geo_lookup.py.
async def _lookup_state(lat: float, lon: float) -> dict[str, Any]:
    """Returns one of:
    {"status": "found", "state_name": ..., "state_code": ..., "county_name": ..., "state_fips": ...}
    {"status": "outside_us"}
    {"status": "error", "message": ...}
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                FCC_AREA_API,
                params={"lat": lat, "lon": lon, "format": "json"},
            )
    except httpx.RequestError as e:
        # Network/DNS/timeout failure -- the caller should know this was an
        # infrastructure problem, not "no state found".
        return {"status": "error", "message": f"network error contacting FCC API: {e}"}

    if response.status_code != 200:
        return {"status": "error", "message": f"FCC API error: HTTP {response.status_code}"}

    data = response.json()
    results = data.get("results", [])

    if not results:
        return {"status": "outside_us"}

    top = results[0]
    return {
        "status": "found",
        "state_name": top["state_name"],
        "state_code": top["state_code"],
        "county_name": top.get("county_name", "unknown"),
        "state_fips": top["state_fips"],
    }


@tool(
    "get_state_for_coordinates",
    "Look up the U.S. state (and county) that a latitude/longitude point falls "
    "within, using the FCC/Census Bureau's authoritative boundary data. "
    "Returns no result if the point is outside the United States (e.g. ocean, "
    "another country).",
    TOOL_INPUT_SCHEMA,
)
async def get_state_for_coordinates(args: dict[str, Any]) -> dict[str, Any]:
    lat, lon = args["latitude"], args["longitude"]
    result = await _lookup_state(lat, lon)

    if result["status"] == "error":
        return {
            "content": [{"type": "text", "text": f"Lookup failed: {result['message']}"}],
            "is_error": True,
        }

    if result["status"] == "outside_us":
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"No U.S. state found for ({lat}, {lon}). The point is "
                        "likely outside the United States (ocean, another "
                        "country, or a territory not covered by this dataset)."
                    ),
                }
            ]
        }

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"State: {result['state_name']} ({result['state_code']}), "
                    f"County: {result['county_name']}, "
                    f"State FIPS: {result['state_fips']}"
                ),
            }
        ]
    }


geo_server = create_sdk_mcp_server(
    name="geo",
    version="1.0.0",
    tools=[get_state_for_coordinates],
)

# ---------------------------------------------------------------------------
# 2. The output contract: always this shape, never free text.
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "latitude": {"type": "number"},
        "longitude": {"type": "number"},
        "state": {"type": ["string", "null"], "description": "Full state name, or null."},
        "state_code": {"type": ["string", "null"], "description": "Two-letter state code, or null."},
        "county": {"type": ["string", "null"]},
        "status": {
            "type": "string",
            "enum": ["found", "outside_us", "error"],
        },
        "notes": {"type": "string"},
    },
    # Every field is required so callers never need `.get()` with a default --
    # nullable fields are still guaranteed to be *present*, just possibly null.
    "required": ["latitude", "longitude", "state", "state_code", "county", "status", "notes"],
}

SYSTEM_PROMPT = (
    "You determine which U.S. state a coordinate falls within. You MUST call "
    "the get_state_for_coordinates tool to answer -- never guess the state "
    "from your own geographic knowledge, since the tool is authoritative and "
    "you are not. Report status='found' when the tool returns a state, "
    "status='outside_us' when the tool returns no result, and status='error' "
    "if the tool call fails. Always echo back the input latitude/longitude."
)


# ---------------------------------------------------------------------------
# 3. The callable operation other code/steps will invoke.
# ---------------------------------------------------------------------------

async def locate_state(latitude: float, longitude: float) -> dict[str, Any]:
    """Given a coordinate, return a dict matching OUTPUT_SCHEMA."""

    # Defense in depth: validate before spending a model call on garbage input.
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        return {
            "latitude": latitude,
            "longitude": longitude,
            "state": None,
            "state_code": None,
            "county": None,
            "status": "error",
            "notes": "Latitude/longitude out of valid range.",
        }

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        mcp_servers={"geo": geo_server},
        allowed_tools=["mcp__geo__get_state_for_coordinates"],
        output_format={"type": "json_schema", "schema": OUTPUT_SCHEMA},
    )

    prompt = f"What U.S. state contains the coordinate latitude={latitude}, longitude={longitude}?"

    try:
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.subtype == "success" and message.structured_output:
                    return message.structured_output
                return {
                    "latitude": latitude,
                    "longitude": longitude,
                    "state": None,
                    "state_code": None,
                    "county": None,
                    "status": "error",
                    "notes": f"Agent run did not produce structured output (subtype={message.subtype}).",
                }
    except Exception as e:
        return {
            "latitude": latitude,
            "longitude": longitude,
            "state": None,
            "state_code": None,
            "county": None,
            "status": "error",
            "notes": f"Agent run raised an exception: {e}",
        }

    # Should not be reached, but keep the contract unbroken if it is.
    return {
        "latitude": latitude,
        "longitude": longitude,
        "state": None,
        "state_code": None,
        "county": None,
        "status": "error",
        "notes": "No result message received from agent run.",
    }


# ---------------------------------------------------------------------------
# 4. Demo / smoke test across the cases that matter: inside a state,
#    near a border, and outside the US entirely.
# ---------------------------------------------------------------------------

TEST_CASES = [
    ("Austin, TX (clearly inside a state)", 30.2672, -97.7431),
    ("Texarkana border area (TX/AR line)", 33.4418, -94.0477),
    ("Atlantic Ocean (outside the US)", 25.0, -70.0),
    ("Invalid input (out-of-range latitude)", 200.0, -97.7431),
]


async def main() -> None:
    for label, lat, lon in TEST_CASES:
        print(f"\n=== {label} ===")
        result = await locate_state(lat, lon)
        print(result)


if __name__ == "__main__":
    asyncio.run(main())
