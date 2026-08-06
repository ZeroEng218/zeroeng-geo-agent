"""
api_keys.py

Self-serve API key issuance for the public MCP endpoint (see mcp_tools.py).

Unlike GEO_API_KEY (a single shared secret only ZeroEng's own backend holds,
used by server.py's /locate-state), these keys are handed out on request to
anyone -- any agent that finds the /register endpoint can get one instantly.
The point isn't to gate access; it's to keep a record of who's calling so
abuse is traceable, without adding signup friction.

Keys are stored as salted-free SHA-256 hashes, never in plaintext -- the raw
key is only ever returned once, at creation time, exactly like a GitHub PAT
or a Stripe secret key.

Backing store: the Supabase project's `api_keys` table (see the
create_api_keys_table migration). Talks to Supabase via the service-role key,
which must never be exposed to callers.
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client

_KEY_PREFIX = "zg_live_"

_client: Optional[Client] = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def generate_api_key() -> str:
    return _KEY_PREFIX + secrets.token_urlsafe(32)


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def create_api_key(name: str, email: str) -> str:
    """Creates and stores a new key, returning the raw value. Not retrievable again."""
    raw_key = generate_api_key()
    _get_client().table("api_keys").insert(
        {"key_hash": hash_key(raw_key), "name": name, "email": email}
    ).execute()
    return raw_key


async def verify_api_key(raw_key: str) -> bool:
    """True if raw_key is a live (non-revoked) registered key.

    Best-effort bumps last_used_at/request_count -- a failure to record usage
    should never block an otherwise-valid call.
    """
    if not raw_key:
        return False

    key_hash = hash_key(raw_key)
    result = (
        _get_client()
        .table("api_keys")
        .select("id, revoked, request_count")
        .eq("key_hash", key_hash)
        .limit(1)
        .execute()
    )

    if not result.data:
        return False

    row = result.data[0]
    if row["revoked"]:
        return False

    try:
        _get_client().table("api_keys").update(
            {
                "last_used_at": datetime.now(timezone.utc).isoformat(),
                "request_count": row["request_count"] + 1,
            }
        ).eq("id", row["id"]).execute()
    except Exception:
        pass

    return True
