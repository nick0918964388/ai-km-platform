"""JWT authentication utilities."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.db.session import get_db

SECRET_KEY = os.getenv("JWT_SECRET", "aikm-secret-key-change-in-production")
if SECRET_KEY == "aikm-secret-key-change-in-production":
    import logging
    logging.getLogger(__name__).warning("JWT_SECRET 使用預設值，請在生產環境設定 JWT_SECRET 環境變數！")
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

    result = await db.execute(text(
        "SELECT id, email, display_name, account_level FROM users WHERE id = :id"
    ), {"id": user_id})
    user = result.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="使用者不存在")

    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.account_level or payload.get("role", "user"),
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
