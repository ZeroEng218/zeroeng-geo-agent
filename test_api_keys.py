"""
Unit tests for api_keys.py's key generation/hashing/verification logic.
Mocks the Supabase client entirely -- no network, no live database.

Run:
    python test_api_keys.py
"""

import asyncio
from unittest.mock import MagicMock, patch

import api_keys
from api_keys import create_api_key, generate_api_key, hash_key, verify_api_key


def _mock_query(return_data):
    query = MagicMock()
    query.execute.return_value = MagicMock(data=return_data)
    return query


def test_generate_and_hash_are_stable_and_distinct():
    key_a = generate_api_key()
    key_b = generate_api_key()

    assert key_a.startswith("zg_live_"), key_a
    assert key_a != key_b, "two generated keys collided"
    assert hash_key(key_a) == hash_key(key_a), "hashing isn't deterministic"
    assert hash_key(key_a) != hash_key(key_b)
    print("test_generate_and_hash_are_stable_and_distinct: PASS")


async def test_create_api_key_stores_hash_not_raw():
    mock_client = MagicMock()
    insert_query = MagicMock()
    insert_query.execute.return_value = MagicMock()
    mock_client.table.return_value.insert.return_value = insert_query

    with patch.object(api_keys, "_get_client", return_value=mock_client):
        raw_key = await create_api_key("Test Agent", "agent@example.com")

    assert raw_key.startswith("zg_live_")
    stored = mock_client.table.return_value.insert.call_args[0][0]
    assert stored["key_hash"] == hash_key(raw_key)
    assert "key" not in stored  # never store the raw value
    assert stored["name"] == "Test Agent"
    assert stored["email"] == "agent@example.com"
    print("test_create_api_key_stores_hash_not_raw: PASS")


async def test_verify_api_key_accepts_live_key():
    mock_client = MagicMock()
    select_chain = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value
    select_chain.execute.return_value = MagicMock(
        data=[{"id": "row-1", "revoked": False, "request_count": 3}]
    )
    update_chain = mock_client.table.return_value.update.return_value.eq.return_value
    update_chain.execute.return_value = MagicMock()

    with patch.object(api_keys, "_get_client", return_value=mock_client):
        result = await verify_api_key("zg_live_whatever")

    assert result is True
    print("test_verify_api_key_accepts_live_key: PASS")


async def test_verify_api_key_rejects_unknown_key():
    mock_client = MagicMock()
    select_chain = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value
    select_chain.execute.return_value = MagicMock(data=[])

    with patch.object(api_keys, "_get_client", return_value=mock_client):
        result = await verify_api_key("zg_live_does_not_exist")

    assert result is False
    print("test_verify_api_key_rejects_unknown_key: PASS")


async def test_verify_api_key_rejects_revoked_key():
    mock_client = MagicMock()
    select_chain = mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value
    select_chain.execute.return_value = MagicMock(
        data=[{"id": "row-2", "revoked": True, "request_count": 10}]
    )

    with patch.object(api_keys, "_get_client", return_value=mock_client):
        result = await verify_api_key("zg_live_revoked")

    assert result is False
    print("test_verify_api_key_rejects_revoked_key: PASS")


async def test_verify_api_key_rejects_empty_key():
    result = await verify_api_key("")
    assert result is False
    print("test_verify_api_key_rejects_empty_key: PASS")


async def main():
    test_generate_and_hash_are_stable_and_distinct()
    await test_create_api_key_stores_hash_not_raw()
    await test_verify_api_key_accepts_live_key()
    await test_verify_api_key_rejects_unknown_key()
    await test_verify_api_key_rejects_revoked_key()
    await test_verify_api_key_rejects_empty_key()
    print("\nAll tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
