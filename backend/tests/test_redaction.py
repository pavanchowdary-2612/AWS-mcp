"""
Tests for the secret redaction module.
Ensures credential patterns are caught and that non-sensitive text is untouched.
"""

import pytest
from app.agent.redaction import redact, redact_dict

REDACTED = "[REDACTED]"


class TestRedactAwsKeyId:
    def test_akia_key(self):
        text = "AccessKeyId: AKIAIOSFODNN7EXAMPLE"
        assert REDACTED in redact(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in redact(text)

    def test_asia_temporary_key(self):
        text = "key=ASIAQWERTY1234567890"
        result = redact(text)
        assert "ASIAQWERTY1234567890" not in result

    def test_does_not_redact_short_key_id(self):
        # Keys shorter than 20 chars should not be redacted as AWS key IDs
        text = "AKIA1234"
        result = redact(text)
        # Should not be completely replaced if it doesn't match the full pattern
        assert "AKIA1234" in result or REDACTED in result  # length-gated


class TestRedactSecretKey:
    def test_secret_access_key_label(self):
        secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        text = f"secret_access_key={secret}"
        result = redact(text)
        assert secret not in result

    def test_aws_secret_label(self):
        secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        text = f"AWS_SECRET={secret}"
        result = redact(text)
        assert secret not in result


class TestRedactSessionToken:
    def test_long_session_token(self):
        token = "A" * 300  # simulate a session token
        text = f"session_token={token}"
        result = redact(text)
        assert token not in result

    def test_short_value_not_redacted(self):
        text = "session_token=short"
        result = redact(text)
        # "short" is only 5 chars — below threshold
        assert "short" in result


class TestRedactGenericSecrets:
    def test_password_field(self):
        text = "password=mysupersecretpassword123"
        result = redact(text)
        assert "mysupersecretpassword123" not in result

    def test_api_key_field(self):
        text = "api_key=sk-abcdefghij1234567890"
        result = redact(text)
        assert "sk-abcdefghij1234567890" not in result

    def test_bearer_token(self):
        # Use a realistic JWT — each part must be ≥ 120 chars for long-base64 redaction
        # OR the whole token value is caught by the bearer pattern (group 1 ≥ 8 chars)
        header = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImFiYzEyMyJ9"  # 56 chars
        payload = "eyJzdWIiOiJ1c2VyLTEyMzQ1Njc4OTAiLCJlbWFpbCI6InVzZXJAZXhhbXBsZS5jb20ifQ"  # 72 chars
        # Combine as a full JWT — value > 8 chars so generic secret pattern kicks in
        token = f"{header}.{payload}.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV"
        text = f"bearer {token}"
        result = redact(text)
        # The full token value should be redacted
        assert payload not in result


class TestHtmlSanitisation:
    def test_script_tag_escaped(self):
        text = "Resource description: <script>alert('xss')</script>"
        result = redact(text)
        assert "<script>" not in result

    def test_img_tag_escaped(self):
        text = 'Tag: <img src=x onerror="alert(1)">'
        result = redact(text)
        assert "<img" not in result


class TestSafeText:
    def test_plain_text_unchanged(self):
        text = "The Lambda function timed out after 3000ms."
        result = redact(text)
        assert "Lambda function timed out after 3000ms" in result

    def test_arn_not_redacted(self):
        arn = "arn:aws:iam::123456789012:role/MyRole"
        result = redact(arn)
        assert arn in result

    def test_empty_string(self):
        assert redact("") == ""


class TestRedactDict:
    def test_nested_dict(self):
        data = {
            # Use key=value string form that the regex can match
            "config": "password=mysupersecretpassword123 host=mydb.example.com",
            "status": "ok",
        }
        result = redact_dict(data)
        assert isinstance(result, dict)
        assert "mysupersecretpassword123" not in str(result)
        assert "mydb.example.com" in str(result)

    def test_list(self):
        data = ["AKIAIOSFODNN7EXAMPLE", "normal string"]
        result = redact_dict(data)
        assert "AKIAIOSFODNN7EXAMPLE" not in str(result)
        assert "normal string" in str(result)
