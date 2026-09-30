"""
Tests for the Redis credential cache.
Uses fakeredis so no real Redis instance is needed.
"""

import json
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from app.auth.sts import CredentialSet


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_creds(seconds_until_expiry: int = 3600, user_id: str = "user-123") -> CredentialSet:
    return CredentialSet(
        access_key_id="AKIAIOSFODNN7EXAMPLE",
        secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token="FQoGZXIvYXdz" * 10,
        expiration=datetime.now(timezone.utc) + timedelta(seconds=seconds_until_expiry),
        role_arn="arn:aws:iam::123456789012:role/TestRole",
        user_id=user_id,
    )


# ── CredentialSet serialisation ────────────────────────────────────────────────


class TestCredentialSetSerialization:
    def test_round_trip(self):
        creds = make_creds()
        d = creds.to_cache_dict()
        restored = CredentialSet.from_cache_dict(d)
        assert restored.access_key_id == creds.access_key_id
        assert restored.secret_access_key == creds.secret_access_key
        assert restored.user_id == creds.user_id
        assert restored.role_arn == creds.role_arn

    def test_expiration_timezone_preserved(self):
        creds = make_creds()
        restored = CredentialSet.from_cache_dict(creds.to_cache_dict())
        assert restored.expiration.tzinfo is not None

    def test_seconds_until_expiry_positive(self):
        creds = make_creds(seconds_until_expiry=1800)
        assert creds.seconds_until_expiry() > 1700

    def test_seconds_until_expiry_negative_when_expired(self):
        creds = make_creds(seconds_until_expiry=-60)
        assert creds.seconds_until_expiry() < 0

    def test_boto3_credentials_keys(self):
        creds = make_creds()
        b3 = creds.boto3_credentials()
        assert "aws_access_key_id" in b3
        assert "aws_secret_access_key" in b3
        assert "aws_session_token" in b3

    def test_env_vars_keys(self):
        from unittest.mock import patch, MagicMock
        mock_settings = MagicMock()
        mock_settings.aws_region = "us-east-1"
        with patch("app.auth.sts.get_settings", return_value=mock_settings):
            creds = make_creds()
            env = creds.env_vars()
        assert "AWS_ACCESS_KEY_ID" in env
        assert "AWS_SECRET_ACCESS_KEY" in env
        assert "AWS_SESSION_TOKEN" in env
        assert "AWS_DEFAULT_REGION" in env

    def test_no_id_token_in_cache_dict(self):
        """ID token must never be stored in the credential cache dict."""
        creds = make_creds()
        d = creds.to_cache_dict()
        assert "id_token" not in d
        assert "token" not in str(d).lower().replace("session_token", "")
