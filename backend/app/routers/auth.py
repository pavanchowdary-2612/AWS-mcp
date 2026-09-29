"""
Auth router — IAM Identity Center OIDC Authorization Code + PKCE flow.

Endpoints
---------
GET  /auth/login        → build PKCE params, store state in Redis, redirect to IdP
GET  /auth/callback     → verify state, exchange code, verify JWT, assume role, set cookie
GET  /auth/me           → return current session info (for frontend auth-state polling)
POST /auth/logout       → delete session from Redis, clear cookie
"""

import logging
import uuid

from fastapi import APIRouter, Cookie, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth.oidc import (
    build_auth_url,
    exchange_code,
    generate_nonce,
    generate_pkce,
    generate_state,
    verify_id_token,
)
from app.auth.sts import assume_role_with_web_identity, get_role_arn_for_user
from app.cache.redis_client import (
    consume_oauth_state,
    delete_session,
    get_aws_credentials,
    get_session_meta,
    store_aws_credentials,
    store_oauth_state,
    store_session_meta,
)
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ── /auth/login ───────────────────────────────────────────────────────────────


@router.get("/login")
async def login(
    request: Request,
    pending_message: str = Query(default="", alias="msg"),
) -> RedirectResponse:
    """
    Initiate the OIDC Authorization Code + PKCE flow.

    The caller may pass ?msg=... to preserve the user's original message across
    the redirect. It is stored server-side (Redis) keyed by the OAuth state.
    """
    settings = get_settings()
    state = generate_state()
    nonce = generate_nonce()
    code_verifier, code_challenge = generate_pkce()

    await store_oauth_state(
        state,
        code_verifier=code_verifier,
        nonce=nonce,
        pending_message=pending_message,
    )

    auth_url = build_auth_url(
        state=state,
        code_challenge=code_challenge,
        nonce=nonce,
        redirect_uri=settings.redirect_uri,
    )
    return RedirectResponse(url=auth_url, status_code=302)





# ── /auth/callback ─────────────────────────────────────────────────────────────


@router.get("/callback")
async def callback(
    request: Request,
    response: Response,
    state: str = Query(...),
    code: str = Query(default=None),
    error: str = Query(default=None),
    error_description: str = Query(default=None),
) -> RedirectResponse:
    """
    Handle the IdP redirect back to the application.
    Verifies state, exchanges code, validates JWT, assumes role, stores session.
    """
    settings = get_settings()

    # IdP sent an error (e.g. user denied access)
    if error:
        logger.warning("OIDC callback error: %s — %s", error, error_description)
        return RedirectResponse(
            url=f"{settings.frontend_url}/?auth_error={error}", status_code=302
        )

    # Verify and consume state (single-use, prevents CSRF)
    oauth_data = await consume_oauth_state(state)
    if oauth_data is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state.")

    code_verifier: str = oauth_data["code_verifier"]
    expected_nonce: str = oauth_data["nonce"]
    pending_message: str = oauth_data.get("pending_message", "")

    # Exchange authorization code for tokens
    try:
        token_resp = exchange_code(
            code=code,
            code_verifier=code_verifier,
            redirect_uri=settings.redirect_uri,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Token exchange failed: %s", exc)
        raise HTTPException(status_code=502, detail="Token exchange with IdP failed.")

    id_token: str = token_resp.get("id_token", "")
    if not id_token:
        raise HTTPException(status_code=502, detail="No id_token in token response.")

    # Verify id_token signature and claims
    try:
        claims = verify_id_token(id_token, expected_nonce=expected_nonce)
    except ValueError as exc:
        logger.warning("ID token verification failed: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    user_id: str = claims.get("sub", "")
    email: str = claims.get("email", "")
    groups: list[str] = claims.get("custom:groups", claims.get("groups", []))
    if isinstance(groups, str):
        groups = [g.strip() for g in groups.split(",") if g.strip()]

    # Resolve role ARN from group mapping (SSM — not hardcoded)
    try:
        role_arn = get_role_arn_for_user(groups)
    except ValueError as exc:
        logger.warning("Role mapping failed for user %s: %s", user_id[:8], exc)
        raise HTTPException(status_code=403, detail=str(exc))

    # Assume role with the verified id_token
    try:
        creds = assume_role_with_web_identity(
            id_token=id_token,
            role_arn=role_arn,
            session_name=user_id,
        )
    except ValueError as exc:
        logger.warning("STS assume role failed: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc))

    # Create a new server-side session
    session_id = str(uuid.uuid4())
    await store_session_meta(
        session_id,
        user_id=user_id,
        email=email,
        groups=groups,
        role_arn=role_arn,
        id_token=id_token,  # stored separately from STS creds
    )
    await store_aws_credentials(session_id, creds)

    # Redirect back to the frontend with the pending message encoded
    import urllib.parse
    redirect_params = "?resumed=1"
    if pending_message:
        redirect_params += f"&msg={urllib.parse.quote(pending_message)}"

    redirect_response = RedirectResponse(
        url=f"{settings.frontend_url}/{redirect_params}", status_code=302
    )
    redirect_response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        max_age=settings.session_cookie_max_age,
        httponly=True,
        secure=not settings.app_base_url.startswith("http://localhost"),
        samesite="lax",
    )
    return redirect_response


# ── /auth/me ──────────────────────────────────────────────────────────────────


@router.get("/me")
async def me(
    request: Request,
    aws_chatbot_session: str = Cookie(default=None, alias=None),
) -> JSONResponse:
    """Return current session info for the frontend auth-state hook."""
    settings = get_settings()
    session_cookie = request.cookies.get(settings.session_cookie_name)

    if not session_cookie:
        return JSONResponse({"authenticated": False})

    meta = await get_session_meta(session_cookie)
    if meta is None:
        return JSONResponse({"authenticated": False, "reason": "session_expired"})

    creds = await get_aws_credentials(session_cookie, meta["user_id"])
    cred_expiry_iso = creds.expiration.isoformat() if creds else None

    return JSONResponse(
        {
            "authenticated": True,
            "user_id": meta["user_id"],
            "email": meta["email"],
            "groups": meta["groups"],
            "cred_expiry": cred_expiry_iso,
            "has_aws_creds": creds is not None,
        }
    )


# ── /auth/logout ──────────────────────────────────────────────────────────────


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Delete the server-side session and clear the session cookie."""
    settings = get_settings()
    session_cookie = request.cookies.get(settings.session_cookie_name)

    if session_cookie:
        await delete_session(session_cookie)

    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(settings.session_cookie_name)
    return resp
