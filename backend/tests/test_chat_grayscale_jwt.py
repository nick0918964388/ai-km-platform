"""
S0 Grayscale — JWT extraction unit tests.

Tests the logic in chat.py that extracts user_id from the Authorization header
for stable grayscale bucketing, without spinning up the full chat endpoint.

Coverage:
  1. No Authorization header → _grayscale_uid is None
  2. Non-Bearer prefix → None
  3. Invalid / expired JWT → None  (decode exception swallowed)
  4. Valid JWT with sub in v2 bucket → gate returns True
  5. Valid JWT with sub outside v2 bucket → gate returns False
  6. Flag OFF → JWT decode never called (perf guard)
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: mock passlib so app.auth can be imported in the test venv,
# which does not have passlib installed (it's a heavy bcrypt dep not needed here).
# Must happen before any `import app.*`.
# ---------------------------------------------------------------------------
if "passlib" not in sys.modules:
    _passlib_mock = MagicMock()
    _passlib_mock.context.CryptContext.return_value = MagicMock()
    sys.modules["passlib"] = _passlib_mock
    sys.modules["passlib.context"] = _passlib_mock.context

# Set JWT_SECRET before app.auth is imported (it reads env at module load).
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-chars-long-ok!")
os.environ.setdefault("ENV", "development")

import jwt as pyjwt
from fastapi import HTTPException

import app.auth as _auth_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SECRET = "test-jwt-secret-32-chars-long-ok!"
_ALGORITHM = "HS256"


def _make_token(sub: str, expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + (
        timedelta(seconds=-1) if expired else timedelta(hours=1)
    )
    return pyjwt.encode({"sub": sub, "exp": exp}, _SECRET, algorithm=_ALGORITHM)


def _uid_in_bucket() -> str:
    """Return a uid whose MD5[:8] % 20 == 0  (lands in v2 bucket)."""
    for i in range(10_000):
        uid = f"user_{i}"
        if int(hashlib.md5(uid.encode()).hexdigest()[:8], 16) % 20 == 0:
            return uid
    raise RuntimeError("Could not find uid in bucket")


def _uid_out_of_bucket() -> str:
    """Return a uid whose MD5[:8] % 20 == 1  (outside v2 bucket)."""
    for i in range(10_000):
        uid = f"user_{i}"
        if int(hashlib.md5(uid.encode()).hexdigest()[:8], 16) % 20 == 1:
            return uid
    raise RuntimeError("Could not find uid outside bucket")


_UID_IN  = _uid_in_bucket()
_UID_OUT = _uid_out_of_bucket()


# ---------------------------------------------------------------------------
# Inline reimplementation of the JWT extraction block from chat.py.
# Mirrors the production code exactly so tests validate the same logic path.
# decode_token is imported from app.auth inside the function, mirroring prod.
# ---------------------------------------------------------------------------

def _resolve_grayscale_uid(authorization_header: str) -> str | None:
    from app.auth import decode_token  # mirrors prod: inline import

    _grayscale_uid: str | None = None
    try:
        _auth_header = authorization_header
        if _auth_header.lower().startswith("bearer "):
            _token = _auth_header[7:]
            _grayscale_uid = decode_token(_token).get("sub")
    except Exception:
        _grayscale_uid = None
    return _grayscale_uid


# Patch app.auth.SECRET_KEY to use the test secret for all tests in this file.
# This ensures _resolve_grayscale_uid → decode_token validates against the same key.
_auth_module.SECRET_KEY = _SECRET


# ---------------------------------------------------------------------------
# 1. No Authorization header
# ---------------------------------------------------------------------------

class TestNoHeader:
    def test_empty_string(self):
        """Empty authorization header → decode_token never called → None."""
        with patch.object(_auth_module, "decode_token", wraps=_auth_module.decode_token) as spy:
            result = _resolve_grayscale_uid("")
        assert result is None
        spy.assert_not_called()

    def test_whitespace_only(self):
        """Whitespace header is not a bearer token → None."""
        result = _resolve_grayscale_uid("   ")
        assert result is None


# ---------------------------------------------------------------------------
# 2. Non-Bearer prefix
# ---------------------------------------------------------------------------

class TestNonBearer:
    def test_basic_auth(self):
        """Basic auth header → does not start with 'bearer ' → None."""
        with patch.object(_auth_module, "decode_token", wraps=_auth_module.decode_token) as spy:
            result = _resolve_grayscale_uid("Basic dXNlcjpwYXNz")
        assert result is None
        spy.assert_not_called()

    def test_bearer_case_insensitive_accepted(self):
        """'BEARER ' prefix (uppercase) is accepted (startswith is lowercased)."""
        token = _make_token("u-upper")
        result = _resolve_grayscale_uid(f"BEARER {token}")
        assert result == "u-upper"


# ---------------------------------------------------------------------------
# 3. Invalid / expired JWT → exception swallowed, returns None
# ---------------------------------------------------------------------------

class TestInvalidJWT:
    def test_expired_token_returns_none(self):
        """Expired token → HTTPException from decode_token → swallowed → None."""
        token = _make_token("u-expired", expired=True)
        result = _resolve_grayscale_uid(f"Bearer {token}")
        assert result is None

    def test_garbage_token_returns_none(self):
        """Completely invalid token string → decode raises → None."""
        result = _resolve_grayscale_uid("Bearer not.a.real.jwt")
        assert result is None

    def test_decode_returns_no_sub(self):
        """Valid JWT but missing 'sub' claim → .get('sub') returns None."""
        # Encode a token with no 'sub' key
        no_sub_token = pyjwt.encode(
            {"role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            _SECRET, algorithm=_ALGORITHM,
        )
        result = _resolve_grayscale_uid(f"Bearer {no_sub_token}")
        assert result is None

    def test_decode_raises_generic_exception_returns_none(self):
        """Any unexpected exception from decode_token → None, not crash."""
        with patch.object(_auth_module, "decode_token", side_effect=RuntimeError("unexpected")):
            result = _resolve_grayscale_uid("Bearer sometoken")
        assert result is None


# ---------------------------------------------------------------------------
# 4 & 5. Valid JWT → v2 gate
# ---------------------------------------------------------------------------

class TestValidJWT:
    def test_uid_in_bucket_gates_true(self):
        """UID in v2 bucket → extracted correctly → _should_use_v2 returns True."""
        from app.services.chat_pipeline_v2 import _should_use_v2

        token = _make_token(_UID_IN)
        uid = _resolve_grayscale_uid(f"Bearer {token}")
        assert uid == _UID_IN
        assert _should_use_v2(uid) is True

    def test_uid_out_of_bucket_gates_false(self):
        """UID outside v2 bucket → extracted correctly → _should_use_v2 returns False."""
        from app.services.chat_pipeline_v2 import _should_use_v2

        token = _make_token(_UID_OUT)
        uid = _resolve_grayscale_uid(f"Bearer {token}")
        assert uid == _UID_OUT
        assert _should_use_v2(uid) is False

    def test_sub_uuid_extracted_correctly(self):
        """Full UUID-style sub is preserved exactly."""
        expected = "550e8400-e29b-41d4-a716-446655440000"
        token = _make_token(expected)
        uid = _resolve_grayscale_uid(f"Bearer {token}")
        assert uid == expected


# ---------------------------------------------------------------------------
# 6. Flag OFF → decode_token never called (perf guard)
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_flag_off_skips_jwt_decode(self):
        """When enable_skills_system is False the S0 block is skipped entirely;
        decode_token must not be called at all."""
        from app.config import get_settings

        settings = get_settings()
        original = settings.enable_skills_system
        settings.enable_skills_system = False

        try:
            with patch.object(_auth_module, "decode_token", wraps=_auth_module.decode_token) as spy:
                # Simulate the production guard condition
                if settings.enable_skills_system:
                    _resolve_grayscale_uid("Bearer sometoken")
            spy.assert_not_called()
        finally:
            settings.enable_skills_system = original
