"""
OIDC / PKCE helpers for the IAM Identity Center authorization flow.

Flow:
  1.  generate_pkce()          → (verifier, challenge)
  2.  build_auth_url(...)      → redirect the user here
  3.  exchange_code(...)       → POST to token endpoint, get raw token dict
  4.  verify_id_token(...)     → validate signature + claims, return payload

Security notes:
  - code_verifier is stored server-side (Redis) and NEVER sent to the browser.
  - ID token signature is verified against Identity Center's JWKS before any
    claim is trusted.
  - The nonce claim is checked to prevent token replay attacks.
"""

import base64
import hashlib
import json
import logging
import secrets
import time
from typing import Any

import httpx
from jose import ExpiredSignatureError, JWTError, jwk, jwt
from jose.utils import base64url_decode

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── PKCE ─────────────────────────────────────────────────────────────────────


def generate_pkce() -> tuple[str, str]:
    """
    Return (code_verifier, code_challenge) per RFC 7636.

    code_verifier  — 43–128 url-safe random chars, kept server-side.
    code_challenge — BASE64URL(SHA-256(verifier)), sent to the auth endpoint.
    """
    verifier = secrets.token_urlsafe(64)  # 86 url-safe chars
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def generate_state() -> str:
    """Return a cryptographically random state token for CSRF protection."""
    return secrets.token_urlsafe(32)


def generate_nonce() -> str:
    """Return a cryptographically random nonce to prevent token replay."""
    return secrets.token_urlsafe(32)


# ── Authorization URL ─────────────────────────────────────────────────────────


def build_auth_url(
    *,
    state: str,
    code_challenge: str,
    nonce: str,
    redirect_uri: str,
) -> str:
    """Construct the IAM Identity Center authorize URL."""
    settings = get_settings()
    discovery = _fetch_discovery()
    authorize_endpoint = discovery["authorization_endpoint"]

    params = {
        "response_type": "code",
        "client_id": settings.identity_center_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{authorize_endpoint}?{qs}"


# ── Token exchange ─────────────────────────────────────────────────────────────


def exchange_code(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """
    Exchange an authorization code for tokens.
    Returns the raw token endpoint response (id_token, access_token, etc.).
    Raises httpx.HTTPStatusError on failure.
    """
    settings = get_settings()
    discovery = _fetch_discovery()
    token_endpoint = discovery["token_endpoint"]

    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.identity_center_client_id,
        "code_verifier": code_verifier,
    }
    if settings.identity_center_client_secret:
        payload["client_secret"] = settings.identity_center_client_secret

    with httpx.Client(timeout=15) as client:
        resp = client.post(token_endpoint, data=payload)
        if resp.status_code >= 400:
            logger.error("Token exchange failed with status %d: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        return resp.json()


# ── Token verification ────────────────────────────────────────────────────────


def verify_id_token(
    id_token: str,
    *,
    expected_nonce: str,
) -> dict[str, Any]:
    """
    Verify *id_token* against Identity Center's public JWKS.

    Checks:
      - Signature validity (RS256/ES256 from JWKS)
      - exp / iat / nbf
      - aud == client_id
      - iss == issuer URL
      - nonce

    Returns the verified payload dict.
    Raises ValueError with a user-friendly message on any failure.
    """
    settings = get_settings()
    try:
        header = _decode_header_unsafe(id_token)
        kid = header.get("kid")
        jwks = _fetch_jwks()
        public_key = _find_key(jwks, kid)

        payload: dict[str, Any] = jwt.decode(
            id_token,
            public_key,
            algorithms=["RS256", "ES256"],
            audience=settings.identity_center_client_id,
            issuer=settings.identity_center_issuer_url,
            options={"verify_at_hash": False},
        )
    except ExpiredSignatureError:
        raise ValueError("ID token has expired — please sign in again.")
    except JWTError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise ValueError(f"ID token verification failed: {exc}") from exc

    # Nonce check (python-jose doesn't enforce nonce automatically)
    if payload.get("nonce") != expected_nonce:
        raise ValueError("ID token nonce mismatch — possible replay attack.")

    return payload


# ── JWKS / discovery (module-level cache) ────────────────────────────────────

_discovery_cache: dict[str, Any] | None = None
_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0
_JWKS_TTL = 600  # re-fetch JWKS every 10 minutes


def _fetch_discovery() -> dict[str, Any]:
    global _discovery_cache
    if _discovery_cache is None:
        settings = get_settings()
        with httpx.Client(timeout=10) as client:
            resp = client.get(settings.oidc_discovery_url)
            resp.raise_for_status()
            _discovery_cache = resp.json()
    return _discovery_cache


def _fetch_jwks() -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.monotonic()
    if _jwks_cache is None or (now - _jwks_fetched_at) > _JWKS_TTL:
        discovery = _fetch_discovery()
        jwks_uri = discovery["jwks_uri"]
        with httpx.Client(timeout=10) as client:
            resp = client.get(jwks_uri)
            resp.raise_for_status()
            _jwks_cache = resp.json()
            _jwks_fetched_at = now
    return _jwks_cache


def _find_key(jwks: dict[str, Any], kid: str | None) -> Any:
    """Find a matching JWK by key ID, or return the first key if kid is absent."""
    keys = jwks.get("keys", [])
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
    if keys:
        return keys[0]
    raise ValueError("No suitable public key found in JWKS.")


def _decode_header_unsafe(token: str) -> dict[str, Any]:
    """Decode the JWT header without verifying the signature (just to get kid/alg)."""
    try:
        header_b64 = token.split(".")[0]
        # Add padding
        padding = 4 - len(header_b64) % 4
        header_b64 += "=" * (padding % 4)
        header_bytes = base64.urlsafe_b64decode(header_b64)
        return json.loads(header_bytes)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Cannot decode JWT header: {exc}") from exc
