"""
STS integration — AssumeRoleWithWebIdentity and SSM-based role mapping.

The group → role ARN mapping is stored in AWS SSM Parameter Store (not
hardcoded), so access-policy changes require only an SSM update, not a
code deploy.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class CredentialSet:
    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime          # tz-aware UTC
    role_arn: str
    user_id: str                  # sub claim from the ID token
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_cache_dict(self) -> dict[str, str]:
        """Serialise to a JSON-safe dict for Redis storage."""
        return {
            "access_key_id": self.access_key_id,
            "secret_access_key": self.secret_access_key,
            "session_token": self.session_token,
            "expiration": self.expiration.isoformat(),
            "role_arn": self.role_arn,
            "user_id": self.user_id,
            "issued_at": self.issued_at.isoformat(),
        }

    @classmethod
    def from_cache_dict(cls, d: dict[str, str]) -> "CredentialSet":
        return cls(
            access_key_id=d["access_key_id"],
            secret_access_key=d["secret_access_key"],
            session_token=d["session_token"],
            expiration=datetime.fromisoformat(d["expiration"]),
            role_arn=d["role_arn"],
            user_id=d["user_id"],
            issued_at=datetime.fromisoformat(d["issued_at"]),
        )

    def boto3_credentials(self) -> dict[str, str]:
        """Return kwargs suitable for boto3.client(..., **creds.boto3_credentials())."""
        return {
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
            "aws_session_token": self.session_token,
        }

    def env_vars(self) -> dict[str, str]:
        """Return env-var dict for injecting into MCP subprocess."""
        return {
            "AWS_ACCESS_KEY_ID": self.access_key_id,
            "AWS_SECRET_ACCESS_KEY": self.secret_access_key,
            "AWS_SESSION_TOKEN": self.session_token,
            "AWS_DEFAULT_REGION": get_settings().aws_region,
        }

    def seconds_until_expiry(self) -> float:
        now = datetime.now(timezone.utc)
        return (self.expiration - now).total_seconds()


# ── Role mapping ──────────────────────────────────────────────────────────────


def get_role_arn_for_user(groups: list[str]) -> str:
    """
    Look up the role ARN for the user's group claims from SSM Parameter Store.

    The SSM parameter contains a JSON object:
        { "GroupName": "arn:aws:iam::123456789012:role/RoleName", ... }

    The first group that has a matching entry wins. Raises ValueError if no
    mapping is found (caller should surface this as a permissions error).
    """
    settings = get_settings()
    try:
        ssm = boto3.client("ssm", region_name=settings.aws_region)
        resp = ssm.get_parameter(
            Name=settings.role_arn_map_ssm_path, WithDecryption=True
        )
        mapping: dict[str, str] = json.loads(resp["Parameter"]["Value"])
    except ClientError as exc:
        logger.warning("Failed to fetch role ARN map from SSM: %s. Using default fallback.", exc)
        return settings.default_role_arn
    except json.JSONDecodeError as exc:
        logger.warning("Role ARN map SSM parameter is not valid JSON: %s. Using default fallback.", exc)
        return settings.default_role_arn

    for group in groups:
        if group in mapping:
            return mapping[group]

    logger.warning(f"No group match in SSM mapping for user groups ({groups}). Using default fallback.")
    return settings.default_role_arn


# ── AssumeRoleWithWebIdentity ─────────────────────────────────────────────────


def assume_role_with_web_identity(
    *,
    id_token: str,
    role_arn: str,
    session_name: str,
) -> CredentialSet:
    """
    Call STS AssumeRoleWithWebIdentity with the user's verified ID token.

    Returns a CredentialSet containing temporary AWS credentials scoped to
    *role_arn*.  Raises ValueError on any STS error (e.g. access denied).
    """
    settings = get_settings()
    sts = boto3.client("sts", region_name=settings.aws_region)

    try:
        resp = sts.assume_role_with_web_identity(
            RoleArn=role_arn,
            RoleSessionName=_sanitise_session_name(session_name),
            WebIdentityToken=id_token,
            DurationSeconds=settings.sts_session_duration,
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        logger.warning(
            "STS AssumeRoleWithWebIdentity failed [%s] for role %s: %s",
            error_code,
            role_arn,
            exc,
        )
        if error_code in ("AccessDenied", "InvalidIdentityToken", "ExpiredTokenException"):
            raise ValueError(
                f"AWS denied access: {exc.response['Error']['Message']}. "
                "Contact your AWS administrator."
            ) from exc
        raise ValueError(f"STS error ({error_code}): {exc.response['Error']['Message']}") from exc

    creds: dict[str, Any] = resp["Credentials"]
    assumed_user_id: str = resp.get("AssumedRoleUser", {}).get("AssumedRoleId", session_name)

    return CredentialSet(
        access_key_id=creds["AccessKeyId"],
        secret_access_key=creds["SecretAccessKey"],
        session_token=creds["SessionToken"],
        expiration=creds["Expiration"],   # already a tz-aware datetime from boto3
        role_arn=role_arn,
        user_id=session_name,             # use the sub claim, not the assumed-role ID
    )


def _sanitise_session_name(name: str) -> str:
    """
    STS session names must match [\\w+=,.@-] and be <= 64 chars.
    Replace anything outside that set with underscores.
    """
    import re
    sanitised = re.sub(r"[^\w+=,.@\-]", "_", name)
    return sanitised[:64]
