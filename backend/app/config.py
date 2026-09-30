"""
Application configuration loaded from environment variables / .env file.
All secrets live here — never hardcoded anywhere else.
"""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── IAM Identity Center OIDC ─────────────────────────────────────────────
    # e.g. https://oidc.us-east-1.amazonaws.com/d-xxxxxxxxxxxx
    identity_center_issuer_url: str = Field(
        ..., description="IAM Identity Center OIDC issuer base URL"
    )
    identity_center_client_id: str = Field(
        ..., description="OIDC application client ID registered in Identity Center"
    )
    # Public PKCE clients have no secret; leave blank if using PKCE-only flow
    identity_center_client_secret: str = Field(
        default="", description="OIDC client secret (empty for PKCE public clients)"
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_base_url: str = Field(
        default="http://localhost:8000",
        description="Public-facing backend base URL (used to build redirect_uri)",
    )
    frontend_url: str = Field(
        default="http://localhost:5173",
        description="Frontend origin (used for CORS and post-login redirect)",
    )
    session_secret: str = Field(
        ..., description="Secret for signing/encrypting server-side session cookies"
    )
    session_cookie_name: str = Field(default="aws_chatbot_session")
    session_cookie_max_age: int = Field(
        default=86400, description="App session max age in seconds (default 24h)"
    )

    # ── AWS ──────────────────────────────────────────────────────────────────
    aws_region: str = Field(default="us-east-1")
    # SSM path holding JSON: { "group-name": "arn:aws:iam::ACCOUNT:role/RoleName" }
    role_arn_map_ssm_path: str = Field(
        default="/aws-chatbot/role-arn-map",
        description="SSM Parameter Store path for group→role ARN mapping",
    )
    # Fallback role ARN if SSM mapping fails or is unavailable
    default_role_arn: str = Field(
        default="",
        description="Fallback IAM Role ARN",
    )
    # STS session duration in seconds (900–43200)
    sts_session_duration: int = Field(default=3600)
    # Refresh credentials when fewer than this many seconds remain
    cred_refresh_threshold_seconds: int = Field(default=300)

    # ── LLM (Groq) ────────────────────────────────────────────────────────────
    groq_api_key: str = Field(..., description="Groq API key from console.groq.com")
    groq_model: str = Field(default="openai/gpt-oss-120b", description="Groq model ID")
    # Maximum sequential tool calls per agent turn (diagnostic cap)
    agent_max_tool_calls: int = Field(default=5)

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://redis:6379/0")
    # Set to true for local dev — uses in-memory fakeredis (no Docker needed)
    use_fake_redis: bool = Field(default=False)
    # TTL for PKCE/state/nonce entries stored during OAuth flow
    oauth_state_ttl_seconds: int = Field(default=900)
    # SETNX lock TTL for the credential refresh guard
    cred_refresh_lock_ttl_seconds: int = Field(default=5)
    # How long to poll waiting for the lock winner to finish refreshing
    cred_refresh_lock_poll_seconds: float = Field(default=6.0)

    # ── MCP ───────────────────────────────────────────────────────────────────
    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="'stdio' spaws a local MCP subprocess; 'http' connects to a remote server",
    )
    # Used only when mcp_transport == "http"
    mcp_http_url: str = Field(
        default="http://localhost:9000/mcp",
        description="URL of the remote MCP server (streamable-HTTP transport)",
    )
    # Space-separated list of awslabs MCP sub-packages to run via uvx (stdio mode)
    mcp_stdio_packages: str = Field(
        default="awslabs.aws-documentation-mcp-server awslabs.aws-core-mcp-server",
        description="MCP packages to launch via 'uvx' for the stdio transport",
    )

    @field_validator("identity_center_issuer_url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @property
    def oidc_discovery_url(self) -> str:
        return f"{self.identity_center_issuer_url}/.well-known/openid-configuration"

    @property
    def redirect_uri(self) -> str:
        return f"{self.app_base_url}/auth/callback"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()  # type: ignore[call-arg]
