"""
Chat router — streaming SSE agent endpoint.

POST /chat
    Body: { "message": "...", "history": [...] }
    Returns: text/event-stream of JSON-encoded agent events

POST /chat/confirm
    Body: { "confirm_token": "...", "agent_state_key": "..." }
    Returns: text/event-stream — executes a pending write action
"""

import json
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent.agent import AgentLoop
from app.cache.redis_client import get_redis, get_session_meta
from app.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# In-memory store for pending write confirmations (keyed by confirm_token).
# In a multi-replica deployment, use Redis instead.
_pending_agents: dict[str, AgentLoop] = {}


# ── Request / Response schemas ────────────────────────────────────────────────


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32_000)
    history: list[dict] = Field(default_factory=list)


class ConfirmRequest(BaseModel):
    confirm_token: str
    agent_state_key: str


# ── Helpers ────────────────────────────────────────────────────────────────────


def _sse_format(data: dict) -> str:
    """Encode a dict as a Server-Sent Event data line."""
    return f"data: {json.dumps(data)}\n\n"


async def _stream_agent(agent: AgentLoop, *, agent_state_key: str | None = None):
    """
    Iterate the agent generator and yield SSE-formatted strings.
    If the agent emits `needs_confirmation`, store it in `_pending_agents`
    keyed by the confirm_token so /chat/confirm can resume it.
    """
    try:
        async for event in agent.run():
            yield _sse_format(event)
            if event.get("type") == "needs_confirmation":
                # Park the agent so it can be resumed after user confirmation
                _pending_agents[event["confirm_token"]] = agent
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent error: %s", exc)
        yield _sse_format({"type": "error", "code": "AGENT_ERROR", "message": str(exc)})
        yield _sse_format({"type": "done"})


async def _stream_confirmed_write(agent: AgentLoop, confirm_token: str):
    """Stream the result of an approved write action."""
    try:
        async for event in agent.execute_confirmed_write(confirm_token=confirm_token):
            yield _sse_format(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Write action error: %s", exc)
        yield _sse_format({"type": "error", "code": "AGENT_ERROR", "message": str(exc)})
        yield _sse_format({"type": "done"})
    finally:
        _pending_agents.pop(confirm_token, None)


# ── POST /chat ─────────────────────────────────────────────────────────────────


@router.post("")
async def chat(request: Request, body: ChatRequest) -> StreamingResponse:
    """
    Main chat endpoint. Returns a streaming SSE response.
    Session is identified by the session cookie (set by /auth/callback).
    """
    settings = get_settings()
    session_id = request.cookies.get(settings.session_cookie_name, "")

    # Build message history in Anthropic format
    messages: list[dict] = list(body.history)
    messages.append({"role": "user", "content": body.message})

    # Create a unique agent state key for this turn (for resume tracking)
    agent_state_key = str(uuid.uuid4())

    agent = AgentLoop(
        session_id=session_id,
        messages=messages,
    )

    return StreamingResponse(
        _stream_agent(agent, agent_state_key=agent_state_key),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── POST /chat/confirm ─────────────────────────────────────────────────────────


@router.post("/confirm")
async def confirm_action(request: Request, body: ConfirmRequest) -> StreamingResponse:
    """
    Resume a paused agent after the user confirms a write action.
    The confirm_token must exactly match what was issued in the
    `needs_confirmation` event.
    """
    agent = _pending_agents.get(body.confirm_token)
    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Confirmation token not found or already used.",
        )

    return StreamingResponse(
        _stream_confirmed_write(agent, body.confirm_token),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── POST /chat/cancel ─────────────────────────────────────────────────────────


@router.post("/cancel")
async def cancel_action(request: Request, body: ConfirmRequest) -> dict:
    """Cancel a pending write action without executing it."""
    agent = _pending_agents.pop(body.confirm_token, None)
    if agent is None:
        raise HTTPException(status_code=404, detail="Confirmation token not found.")
    return {"status": "cancelled"}
