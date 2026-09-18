# ZeroEng Geo Lookup Service

An MCP-powered geolocation service that identifies the U.S. state and county associated with latitude and longitude coordinates.

The service uses authoritative Census-area data rather than relying on a language model's geographic knowledge. It exposes both a protected backend endpoint and a public streamable HTTP MCP endpoint for registered AI agents.

## Main capabilities

- Determine a U.S. state from coordinates.
- Return state code and county information when available.
- Expose the lookup as an MCP tool named `get_state_for_coordinates`.
- Provide API-key registration for external agents.

## Endpoints

- `GET /health` — liveness check.
- `POST /locate-state` — protected backend lookup.
- `POST /register` — register an agent and receive an API key.
- `/mcp` — streamable HTTP MCP server.

See the service documentation and source files for environment variables, authentication, local development, and extension instructions.
