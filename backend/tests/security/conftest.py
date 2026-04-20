"""
Fixtures for 012 router security PoCs (T061a-e).

Provides JWT minting helpers for each role (uses the same secret/algorithm as
backend/app/auth.py) plus a live-endpoint sniff helper.

Roles requested in T061a-e:
  - admin / maint_manager / maint_tech / analyst / viewer
Note: in production DB users.account_level today only contains {"admin","user"}.
`_normalize_role()` in backend/app/routers/maximo.py maps unknown -> "viewer".
For the PoCs we therefore construct synthetic tokens that would, if the role were
read from JWT claim, grant the attacker that role. The defense being tested is
that the backend RE-FETCHES the role from DB in `get_current_user` (auth.py L80)
regardless of the JWT claim.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import pytest

# Mirror backend/app/auth.py — JWT_SECRET must be set in the test environment.
# In CI / docker exec context, the env var is inherited from the container.
SECRET_KEY = os.getenv("JWT_SECRET", "")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET env var not set — cannot mint test tokens. "
        "Run inside the container: docker exec -e JWT_SECRET=... aikm-backend pytest ..."
    )
ALGORITHM = "HS256"

BACKEND_URL = os.getenv("AIKM_BACKEND_URL", "http://192.168.1.11:8000")
API_KEY = os.getenv("AIKM_API_KEY", "")

# Production admin user id (per SSH inspection 2026-04-20)
REAL_ADMIN_USER_ID = "87564faa-661c-4110-86b4-30c4f387306b"


def mint_token(
    user_id: str,
    role: str,
    secret: str = SECRET_KEY,
    algorithm: str = ALGORITHM,
    extra: dict[str, Any] | None = None,
    exp_hours: int = 1,
) -> str:
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=exp_hours),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm=algorithm)


@pytest.fixture(scope="session")
def admin_token() -> str:
    """Real admin user — account_level='admin' in DB. JWT claim=admin."""
    return mint_token(REAL_ADMIN_USER_ID, "admin")


@pytest.fixture(scope="session")
def analyst_token_forged() -> str:
    """Mint a token CLAIMING analyst role for the real admin user id.
    Role will be OVERRIDDEN by DB lookup per auth.py L80."""
    return mint_token(REAL_ADMIN_USER_ID, "analyst")


@pytest.fixture(scope="session")
def viewer_token_forged() -> str:
    return mint_token(REAL_ADMIN_USER_ID, "viewer")


@pytest.fixture(scope="session")
def maint_tech_token_forged() -> str:
    return mint_token(REAL_ADMIN_USER_ID, "maint_tech")


@pytest.fixture(scope="session")
def maint_manager_token_forged() -> str:
    return mint_token(REAL_ADMIN_USER_ID, "maint_manager")


@pytest.fixture(scope="session")
def nonexistent_user_token() -> str:
    """Valid signature, user_id that does NOT exist in DB.
    Should be rejected with 401 per auth.py L73-74."""
    return mint_token("00000000-0000-0000-0000-000000000000", "admin")


@pytest.fixture(scope="session")
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture(scope="session")
def default_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["x-api-key"] = API_KEY
    return h


@pytest.fixture(scope="session")
def backend_live(backend_url: str, default_headers: dict) -> bool:
    """True if http://192.168.1.11:8000/health returns 200."""
    import httpx
    try:
        r = httpx.get(f"{backend_url}/health", headers=default_headers, timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False
