"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid

from app.db.session import get_db
from app.auth import hash_password, verify_password, create_access_token, get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str = ""


class AuthResponse(BaseModel):
    success: bool
    token: str = ""
    user: dict = {}
    message: str = ""


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email + password, returns JWT token."""
    result = await db.execute(text(
        "SELECT id, email, password_hash, display_name, account_level FROM users WHERE email = :email"
    ), {"email": req.email})
    user = result.fetchone()

    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")

    # Update last_login
    await db.execute(text(
        "UPDATE users SET last_login = NOW() WHERE id = :id"
    ), {"id": user.id})
    await db.commit()

    token = create_access_token(user.id, user.account_level)

    return AuthResponse(
        success=True,
        token=token,
        user={
            "id": user.id,
            "email": user.email,
            "name": user.display_name or user.email.split("@")[0],
            "role": user.account_level,
        },
    )


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    """Register a new user. Requires admin token."""
    exists = await db.execute(text(
        "SELECT id FROM users WHERE email = :email"
    ), {"email": req.email})
    if exists.fetchone():
        raise HTTPException(status_code=409, detail="此 Email 已被註冊")

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    display_name = req.display_name or req.email.split("@")[0]

    await db.execute(text("""
        INSERT INTO users (id, email, password_hash, display_name, account_level)
        VALUES (:id, :email, :hash, :name, :role)
    """), {
        "id": user_id,
        "email": req.email,
        "hash": hashed,
        "name": display_name,
        "role": "user",
    })
    await db.commit()

    token = create_access_token(user_id, "user")

    return AuthResponse(
        success=True,
        token=token,
        user={
            "id": user_id,
            "email": req.email,
            "name": display_name,
            "role": "user",
        },
    )


@router.post("/setup", response_model=AuthResponse)
async def initial_setup(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create initial admin account. Only works when no users exist."""
    count = await db.execute(text("SELECT COUNT(*) FROM users"))
    if count.scalar() > 0:
        raise HTTPException(status_code=403, detail="系統已初始化，無法再次設定")

    user_id = str(uuid.uuid4())
    hashed = hash_password(req.password)
    display_name = req.display_name or "Admin"

    await db.execute(text("""
        INSERT INTO users (id, email, password_hash, display_name, account_level)
        VALUES (:id, :email, :hash, :name, 'admin')
    """), {"id": user_id, "email": req.email, "hash": hashed, "name": display_name})

    # Auto-assign admin permission group
    admin_group = await db.execute(text("SELECT id FROM permission_groups WHERE name = 'admin'"))
    group = admin_group.fetchone()
    if group:
        await db.execute(text(
            "INSERT INTO user_permissions (user_id, group_id) VALUES (:uid, :gid) ON CONFLICT DO NOTHING"
        ), {"uid": user_id, "gid": group.id})

    await db.commit()

    token = create_access_token(user_id, "admin")
    return AuthResponse(
        success=True,
        token=token,
        user={"id": user_id, "email": req.email, "name": display_name, "role": "admin"},
    )


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current user info from JWT token."""
    return user
