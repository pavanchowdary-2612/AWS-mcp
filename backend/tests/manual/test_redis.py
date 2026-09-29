"""
Redis connectivity and functionality test.
Run from the backend/ directory:
    python test_redis.py
"""
import asyncio
import json
import os
import sys
import time

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

USE_FAKE_REDIS = os.getenv("USE_FAKE_REDIS", "false").lower() in ("true", "1", "yes")
REDIS_URL      = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def get_client():
    if USE_FAKE_REDIS:
        import fakeredis.aioredis as fakeredis_async
        return fakeredis_async.FakeRedis(decode_responses=True), "fakeredis (in-memory)"
    else:
        import redis.asyncio as aioredis
        client = await aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        return client, f"Redis @ {REDIS_URL}"


async def main():
    print("=" * 55)
    print("  Redis Connectivity & Functionality Test")
    print("=" * 55)

    try:
        redis, backend = await get_client()
    except Exception as e:
        print(f"\n  FAILED to create Redis client: {e}\n")
        sys.exit(1)

    print(f"  Backend : {backend}")
    print("-" * 55)

    passed = 0
    failed = 0

    async def check(name, coro):
        nonlocal passed, failed
        try:
            result = await coro
            print(f"  [PASS] {name}: {result}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    # ── 1. PING ────────────────────────────────────────────────────────────────
    await check("PING", redis.ping())

    # ── 2. SET / GET ───────────────────────────────────────────────────────────
    await redis.set("test:hello", "world")
    await check("SET/GET", redis.get("test:hello"))

    # ── 3. SETEX (TTL) ────────────────────────────────────────────────────────
    await redis.setex("test:ttl_key", 60, "temp_value")
    ttl = await redis.ttl("test:ttl_key")
    await check("SETEX + TTL", asyncio.coroutine(lambda: ttl)())

    # ── 4. JSON blob (simulates session meta storage) ─────────────────────────
    meta = {"user_id": "test-user", "email": "test@example.com", "groups": ["dev"], "role_arn": "arn:aws:iam::123:role/Test"}
    await redis.setex("session:test-session:meta", 3600, json.dumps(meta))
    raw = await redis.get("session:test-session:meta")
    parsed = json.loads(raw)
    await check("JSON session meta SET/GET", asyncio.coroutine(lambda: parsed["user_id"])())

    # ── 5. SETNX (lock simulation) ─────────────────────────────────────────────
    acquired1 = await redis.set("test:lock", "1", nx=True, ex=5)
    acquired2 = await redis.set("test:lock", "1", nx=True, ex=5)  # should fail
    await redis.delete("test:lock")
    await check("SETNX lock acquire=True", asyncio.coroutine(lambda: acquired1)())
    await check("SETNX lock 2nd acquire=False (expected)", asyncio.coroutine(lambda: acquired2 is None)())

    # ── 6. GETDEL (OAuth state consume) ───────────────────────────────────────
    await redis.set("oauth:test-state", json.dumps({"code_verifier": "abc", "nonce": "xyz"}))
    raw_del = await redis.getdel("oauth:test-state")
    gone = await redis.get("oauth:test-state")
    await check("GETDEL (atomic get+delete)", asyncio.coroutine(lambda: raw_del is not None and gone is None)())

    # ── 7. DELETE ─────────────────────────────────────────────────────────────
    await redis.delete("test:hello", "test:ttl_key", "session:test-session:meta")
    await check("DELETE cleanup", redis.exists("test:hello"))

    # ── Summary ───────────────────────────────────────────────────────────────
    print("-" * 55)
    print(f"\n  Results: {passed} passed, {failed} failed\n")

    if failed == 0:
        print("  Redis is WORKING correctly!\n")
    else:
        print("  Some Redis tests FAILED. Check output above.\n")
        sys.exit(1)


# Python 3.10 compat — coroutine() was removed; use simple helper
import types
def _make_coro(val):
    async def _inner():
        return val
    return _inner()

# Patch asyncio.coroutine references (deprecated in 3.11+)
asyncio.coroutine = lambda f: (lambda *a, **kw: _make_coro(f(*a, **kw)))

if __name__ == "__main__":
    asyncio.run(main())
