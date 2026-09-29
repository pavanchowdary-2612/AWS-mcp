"""
Redis-backed credential cache with per-session SETNX refresh locking.

Key layout
----------
session:{session_id}:aws_creds   JSON blob (TTL = STS expiration)
session:{session_id}:refresh_lock  SETNX lock (TTL ~5s)
oauth:{state}                    PKCE state/verifier/nonce (TTL 300s)

Security invariants
-------------------
- user_id inside the cached credential is verified against the requesting
  session's authenticated identity before returning credentials.
- The ID token is NEVER stored alongside STS credentials.
- Concurrent AssumeRole calls are serialised per session via SETNX; losers
  poll up to cred_refresh_lock_poll_seconds for the winner's result.
"""

import asyncio
import json
import logging
import time
from typing import Any

import redis.asyncio as aioredis

from app.auth.sts import CredentialSet, assume_role_with_web_identity
from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Connection pool (module-level singleton — safe; it's not user-scoped) ─────

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool

    settings = get_settings()

    if settings.use_fake_redis:
        # Local dev mode: in-memory Redis (no Docker needed)
        import fakeredis.aioredis as fakeredis_async  # type: ignore[import]
        logger.warning(
            "USE_FAKE_REDIS=true — using in-memory fakeredis. "
            "Sessions will NOT persist across restarts."
        )
        _redis_pool = fakeredis_async.FakeRedis(decode_responses=True)
        return _redis_pool

    _redis_pool = await aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=50,
    )
    return _redis_pool


# ── Key helpers ───────────────────────────────────────────────────────────────


def _creds_key(session_id: str) -> str:
    return f"session:{session_id}:aws_creds"


def _lock_key(session_id: str) -> str:
    return f"session:{session_id}:refresh_lock"


def _oauth_key(state: str) -> str:
    return f"oauth:{state}"


# ── Credential storage ────────────────────────────────────────────────────────


async def store_aws_credentials(session_id: str, creds: CredentialSet) -> None:
    """Persist *creds* in Redis. TTL is set to the STS expiration time."""
    redis = await get_redis()
    ttl_seconds = max(int(creds.seconds_until_expiry()), 1)
    payload = json.dumps(creds.to_cache_dict())
    await redis.set(_creds_key(session_id), payload, ex=ttl_seconds)
    logger.debug(
        "Stored credentials for session %s (TTL %ds, role %s)",
        session_id[:8],
        ttl_seconds,
        creds.role_arn,
    )


async def get_aws_credentials(
    session_id: str,
    expected_user_id: str,
) -> CredentialSet | None:
    """
    Retrieve cached credentials, verifying user_id matches *expected_user_id*.
    Returns None if not found, expired (TTL handled by Redis), or user_id mismatch.
    """
    redis = await get_redis()
    raw = await redis.get(_creds_key(session_id))
    if raw is None:
        return None

    try:
        data: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Corrupt credential blob for session %s", session_id[:8])
        await redis.delete(_creds_key(session_id))
        return None

    cached_user_id = data.get("user_id", "")
    if cached_user_id != expected_user_id:
        logger.warning(
            "user_id mismatch for session %s: expected %s, got %s",
            session_id[:8],
            expected_user_id[:8],
            cached_user_id[:8],
        )
        return None

    return CredentialSet.from_cache_dict(data)


async def delete_aws_credentials(session_id: str) -> None:
    redis = await get_redis()
    await redis.delete(_creds_key(session_id))


# ── Credential refresh with SETNX lock ───────────────────────────────────────


async def get_or_refresh_credentials(
    *,
    session_id: str,
    user_id: str,
    id_token: str,
    role_arn: str,
) -> CredentialSet:
    """
    Return valid credentials for *session_id*, refreshing via STS if needed.

    If the credentials expire in < threshold seconds, acquire a per-session
    SETNX lock and refresh.  Concurrent callers that lose the lock poll until
    the winner writes the new credentials.
    """
    settings = get_settings()
    threshold = settings.cred_refresh_threshold_seconds

    # Fast path — valid cached creds
    creds = await get_aws_credentials(session_id, user_id)
    if creds is not None and creds.seconds_until_expiry() > threshold:
        return creds

    # Slow path — need refresh; try to acquire the lock
    redis = await get_redis()
    lock_key = _lock_key(session_id)
    lock_ttl = settings.cred_refresh_lock_ttl_seconds
    acquired = await redis.set(lock_key, "1", nx=True, ex=lock_ttl)

    if acquired:
        # We won the lock — do the actual refresh
        try:
            logger.info("Refreshing AWS credentials for session %s", session_id[:8])
            new_creds = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: assume_role_with_web_identity(
                    id_token=id_token,
                    role_arn=role_arn,
                    session_name=user_id,
                ),
            )
            await store_aws_credentials(session_id, new_creds)
            return new_creds
        finally:
            await redis.delete(lock_key)
    else:
        # We lost the lock — poll for the winner's result
        deadline = time.monotonic() + settings.cred_refresh_lock_poll_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(0.3)
            refreshed = await get_aws_credentials(session_id, user_id)
            if refreshed is not None and refreshed.seconds_until_expiry() > threshold:
                return refreshed
        # If we still don't have valid creds after polling, try once more directly
        final = await get_aws_credentials(session_id, user_id)
        if final is not None:
            return final
        raise RuntimeError(
            "Could not obtain valid AWS credentials after waiting for lock. "
            "Please retry your request."
        )


# ── OAuth state storage (for PKCE flow) ───────────────────────────────────────


async def store_oauth_state(
    state: str,
    *,
    code_verifier: str,
    nonce: str,
    pending_message: str = "",
) -> None:
    """Store PKCE state, verifier, nonce, and optional pending message."""
    settings = get_settings()
    redis = await get_redis()
    payload = json.dumps(
        {
            "code_verifier": code_verifier,
            "nonce": nonce,
            "pending_message": pending_message,
        }
    )
    await redis.set(_oauth_key(state), payload, ex=settings.oauth_state_ttl_seconds)


async def consume_oauth_state(state: str) -> dict[str, str] | None:
    """
    Retrieve and atomically delete the OAuth state entry.
    Returns None if the state is unknown or expired.
    """
    redis = await get_redis()
    key = _oauth_key(state)
    raw = await redis.getdel(key)  # atomic get-and-delete (Redis ≥ 6.2)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── Session metadata (user info stored after login) ───────────────────────────


def _session_meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"


async def store_session_meta(
    session_id: str,
    *,
    user_id: str,
    email: str,
    groups: list[str],
    role_arn: str,
    id_token: str,
) -> None:
    """
    Store lightweight session metadata (user info + role ARN + *encrypted* id_token).
    id_token is needed for silent credential refresh; it is stored separately
    from the STS creds and never returned to the browser.
    TTL matches the app session max age.
    """
    settings = get_settings()
    redis = await get_redis()
    payload = json.dumps(
        {
            "user_id": user_id,
            "email": email,
            "groups": groups,
            "role_arn": role_arn,
            "id_token": id_token,  # needed for re-assume; never sent to client
        }
    )
    await redis.set(
        _session_meta_key(session_id),
        payload,
        ex=settings.session_cookie_max_age,
    )


async def get_session_meta(session_id: str) -> dict[str, Any] | None:
    redis = await get_redis()
    raw = await redis.get(_session_meta_key(session_id))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def delete_session(session_id: str) -> None:
    redis = await get_redis()
    await redis.delete(
        _creds_key(session_id),
        _lock_key(session_id),
        _session_meta_key(session_id),
    )
