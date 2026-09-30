"""
Tests the actual app redis_client module end-to-end.
Run from the backend/ directory:
    python test_redis_app.py
"""
import asyncio
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=".env")
except ImportError:
    pass


async def main():
    from app.cache.redis_client import (
        get_redis,
        store_session_meta,
        get_session_meta,
        delete_session,
        store_oauth_state,
        consume_oauth_state,
    )

    print("=" * 55)
    print("  App redis_client Module Test")
    print("=" * 55)

    passed = 0
    failed = 0

    def ok(label, value=""):
        nonlocal passed
        passed += 1
        print(f"  [PASS] {label}: {value}")

    def fail(label, err):
        nonlocal failed
        failed += 1
        print(f"  [FAIL] {label}: {err}")

    # 1. get_redis + PING
    try:
        redis = await get_redis()
        pong = await redis.ping()
        ok("get_redis + PING", pong)
    except Exception as e:
        fail("get_redis + PING", e)

    # 2. store_session_meta
    try:
        await store_session_meta(
            "test-session-001",
            user_id="user-abc",
            email="user@example.com",
            groups=["dev", "admin"],
            role_arn="arn:aws:iam::123456789:role/DevRole",
            id_token="fake-id-token-xyz",
        )
        ok("store_session_meta")
    except Exception as e:
        fail("store_session_meta", e)

    # 3. get_session_meta
    try:
        meta = await get_session_meta("test-session-001")
        assert meta is not None
        assert meta["user_id"] == "user-abc"
        assert meta["email"] == "user@example.com"
        assert "dev" in meta["groups"]
        ok("get_session_meta", "user_id=" + meta["user_id"])
    except Exception as e:
        fail("get_session_meta", e)

    # 4. store_oauth_state + consume_oauth_state
    try:
        await store_oauth_state(
            "state-abc123",
            code_verifier="verifier-xyz",
            nonce="nonce-999",
            pending_message="hello world",
        )
        data = await consume_oauth_state("state-abc123")
        assert data is not None
        assert data["code_verifier"] == "verifier-xyz"
        assert data["nonce"] == "nonce-999"
        # Second consume should return None (atomically deleted)
        data2 = await consume_oauth_state("state-abc123")
        assert data2 is None
        ok("store/consume_oauth_state", "atomic delete works")
    except Exception as e:
        fail("store/consume_oauth_state", e)

    # 5. delete_session
    try:
        await delete_session("test-session-001")
        gone = await get_session_meta("test-session-001")
        assert gone is None
        ok("delete_session", "cleaned up")
    except Exception as e:
        fail("delete_session", e)

    print("-" * 55)
    print(f"\n  Results: {passed} passed, {failed} failed\n")

    if failed == 0:
        print("  App redis_client is WORKING correctly!\n")
    else:
        print("  Some tests FAILED. Check output above.\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
