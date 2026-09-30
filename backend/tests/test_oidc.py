"""
Tests for OIDC helper functions.
"""

import hashlib
import base64

import pytest

from app.auth.oidc import generate_pkce, generate_state, generate_nonce


class TestGeneratePkce:
    def test_returns_tuple_of_two_strings(self):
        result = generate_pkce()
        assert isinstance(result, tuple)
        assert len(result) == 2
        verifier, challenge = result
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_verifier_length(self):
        verifier, _ = generate_pkce()
        # secrets.token_urlsafe(64) produces 86 chars
        assert 43 <= len(verifier) <= 128

    def test_challenge_is_sha256_of_verifier(self):
        verifier, challenge = generate_pkce()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        assert challenge == expected

    def test_challenge_no_padding(self):
        _, challenge = generate_pkce()
        assert "=" not in challenge

    def test_each_call_produces_unique_values(self):
        v1, c1 = generate_pkce()
        v2, c2 = generate_pkce()
        assert v1 != v2
        assert c1 != c2


class TestGenerateState:
    def test_is_string(self):
        assert isinstance(generate_state(), str)

    def test_minimum_length(self):
        # token_urlsafe(32) → 43 chars
        assert len(generate_state()) >= 32

    def test_unique(self):
        assert generate_state() != generate_state()


class TestGenerateNonce:
    def test_is_string(self):
        assert isinstance(generate_nonce(), str)

    def test_unique(self):
        assert generate_nonce() != generate_nonce()
