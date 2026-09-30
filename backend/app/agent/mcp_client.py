"""
Per-request MCP client factory.

Each call to `create_mcp_client()` spawns a fresh MCP connection using the
session-scoped STS credentials for that specific user.  There is no shared
global MCP client — isolation is enforced at the factory level.

Two transports are supported (configured via MCP_TRANSPORT env var):
  - stdio: launches a local `uvx` subprocess; AWS env vars are injected.
  - http:  connects to a remote MCP server via Streamable HTTP.

Usage (inside an async context):
    async with create_mcp_client(creds) as (session, tools):
        result = await session.call_tool(tool_name, arguments)
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, AsyncExitStack
from typing import Any, AsyncGenerator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

from app.auth.sts import CredentialSet
from app.config import get_settings

logger = logging.getLogger(__name__)

class MultiSession:
    def __init__(self, sessions_and_tools):
        self.tool_map = {}
        self.all_tools = []
        for session, tools in sessions_and_tools:
            for t in tools:
                self.tool_map[t.name] = session
                self.all_tools.append(t)

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        if name not in self.tool_map:
            raise ValueError(f"Tool {name} not found in any connected MCP server.")
        session = self.tool_map[name]
        return await session.call_tool(name, args)

@asynccontextmanager
async def create_mcp_client(
    creds: CredentialSet,
) -> AsyncGenerator[tuple[MultiSession, list[Tool]], None]:
    """
    Async context manager that yields (session_router, combined_tools) for all configured MCP servers.
    """
    settings = get_settings()

    if settings.mcp_transport == "stdio":
        async with _stdio_multi_client(creds, settings) as result:
            yield result
    else:
        # For HTTP, we just support one server currently
        async with _http_client(creds, settings) as (session, tools):
            router = MultiSession([(session, tools)])
            yield router, tools


@asynccontextmanager
async def _stdio_multi_client(
    creds: CredentialSet,
    settings: Any,
) -> AsyncGenerator[tuple[MultiSession, list[Tool]], None]:
    """Launch local MCP subprocesses with injected AWS credentials."""
    packages = settings.mcp_stdio_packages.split()
    if not packages:
        raise ValueError("MCP_STDIO_PACKAGES is empty — cannot start MCP servers.")

    env = {**os.environ, **creds.env_vars()}
    env["HOME"] = "/tmp/mcp_home"
    os.makedirs(env["HOME"], exist_ok=True)
    import shutil
    import sys
    from pathlib import Path
    
    uvx_cmd = shutil.which("uvx")
    if not uvx_cmd:
        fallback = Path(sys.prefix) / "Scripts" / "uvx.exe"
        uvx_cmd = str(fallback) if fallback.exists() else "uvx"

    async with AsyncExitStack() as stack:
        sessions_and_tools = []
        for package in packages:
            server_params = StdioServerParameters(
                command=uvx_cmd,
                args=["--with", "mcp==1.11.0", package],
                env=env,
            )
            logger.debug("Spawning MCP stdio subprocess: uvx %s", package)
            try:
                read, write = await stack.enter_async_context(stdio_client(server_params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools_response = await session.list_tools()
                sessions_and_tools.append((session, tools_response.tools))
                logger.debug("MCP stdio session %s ready — %d tools", package, len(tools_response.tools))
            except Exception as e:
                logger.error("Failed to initialize MCP server %s: %s", package, e)
                
        if not sessions_and_tools:
            raise RuntimeError("All MCP servers failed to initialize.")
            
        router = MultiSession(sessions_and_tools)
        yield router, router.all_tools


@asynccontextmanager
async def _http_client(
    creds: CredentialSet,
    settings: Any,
) -> AsyncGenerator[tuple[ClientSession, list[Tool]], None]:
    """Connect to a remote MCP server via Streamable HTTP."""
    import httpx

    headers = {
        "X-AWS-Access-Key-Id": creds.access_key_id,
        "X-AWS-Secret-Access-Key": creds.secret_access_key,
        "X-AWS-Session-Token": creds.session_token,
    }
    logger.debug("Connecting to remote MCP server at %s", settings.mcp_http_url)

    async with httpx.AsyncClient(headers=headers, timeout=30) as http_client:
        async with streamable_http_client(settings.mcp_http_url, http_client=http_client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_response = await session.list_tools()
                tools: list[Tool] = tools_response.tools
                logger.debug(
                    "MCP HTTP session ready — %d tools available", len(tools)
                )
                yield session, tools
