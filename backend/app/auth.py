"""JWT authentication utilities."""
import os
import secrets
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

_logger = logging.getLogger(__name__)

_INSECURE_DEFAULT = "aikm-secret-key-change-in-production"
_ENV = os.getenv("ENV", "production").lower()

_raw_secret = os.getenv("JWT_SECRET", "")

if not _raw_secret or _raw_secret == _INSECURE_DEFAULT:
    if _ENV == "development":
        # Dev-only: generate a random secret that lives only for this process lifetime.
        _raw_secret = secrets.token_hex(32)
        _logger.warning(
            "JWT_SECRET not set (or uses insecure default) — "
            "generated an ephemeral dev secret for this process. "
            "Tokens will be invalidated on next restart. "
            "Set JWT_SECRET in your .env for persistent sessions."
        )
    else:
        raise RuntimeError(
            "SECURITY: JWT_SECRET env var is missing or equals the insecure literal default. "
            "Generate a strong secret with: openssl rand -hex 32 "
            "and set JWT_SECRET in the backend environment before starting."
        )

SECRET_KEY: str = _raw_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str, extra: dict = None) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已過期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="無效的 Token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Extract and validate JWT token. Returns user dict with id, role, email, etc.
    If no token provided, returns a guest user for backward compatibility."""
    if not credentials:
        return {"id": "guest", "role": "guest", "email": None, "display_name": "訪客"}

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="無效的 Token")

    result = await db.execute(text("""
        SELECT u.id, u.email, u.display_name, u.account_level,
               up.section, up.workshop
        FROM users u
        LEFT JOIN user_permissions up ON up.user_id = u.id
        WHERE u.id = :id
        LIMIT 1
    """), {"id": user_id})
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="使用者不存在")

    role = user.account_level or payload.get("role", "user")
    section = user.section or None
    workshop = user.workshop or None

    # Guard: maint_tech with NULL section must not fall through to full-table access.
    # Callers that gate on `if section:` will drop the row filter → log a warning.
    if role == "maint_tech" and not section:
        _logger.warning(
            "maint_tech user %s has NULL section in user_permissions — "
            "row filters will be DROPPED (zero-row policy applies at tool layer).",
            user_id,
        )

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": role,
        "section": section,
        "workshop": workshop,
    }


async def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Require valid JWT token. No guest fallback."""
    if not credentials:
        raise HTTPException(status_code=401, detail="請先登入")
    return await get_current_user(credentials, db)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")
    return user


async def require_admin_strict(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Require admin role — re-reads account_level from DB on every request.

    Does NOT trust the JWT role claim.  Even if the token says role=admin,
    this dependency re-queries the users table so a demoted admin is blocked
    immediately without waiting for token expiry.

    Raises:
        HTTPException(401): Missing or invalid JWT, or user no longer exists.
        HTTPException(403): User exists but account_level != 'admin'.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="請先登入")

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="無效的 Token")

    result = await db.execute(
        text("SELECT id, email, display_name, account_level FROM users WHERE id = :id"),
        {"id": user_id},
    )
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="使用者不存在")

    db_role: str = user.account_level or ""
    if db_role != "admin":
        raise HTTPException(status_code=403, detail="需要管理員權限")

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": db_role,
    }
