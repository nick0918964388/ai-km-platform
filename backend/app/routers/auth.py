"""Authentication API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
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


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    """List all users with their permission groups. Requires admin."""
    result = await db.execute(text("""
        SELECT u.id, u.email, u.display_name, u.account_level, u.last_login,
               pg.name as group_name, pg.display_name as group_display,
               up.section, up.workshop
        FROM users u
        LEFT JOIN user_permissions up ON up.user_id = u.id
        LEFT JOIN permission_groups pg ON pg.id = up.group_id
        ORDER BY u.created_at DESC
    """))
    users = []
    for r in result.fetchall():
        users.append({
            "id": r.id,
            "email": r.email,
            "display_name": r.display_name,
            "role": r.account_level,
            "last_login": r.last_login.isoformat() if r.last_login else None,
            "group_name": r.group_name,
            "group_display": r.group_display,
            "section": r.section,
            "workshop": r.workshop,
        })
    return {"users": users}


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    group_name: Optional[str] = None
    section: Optional[str] = None
    workshop: Optional[str] = None


@router.patch("/users/{user_id}")
async def update_user(user_id: str, req: UpdateUserRequest, db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    """Update user role, permission group, section, workshop."""
    # Check user exists
    exists = await db.execute(text("SELECT id FROM users WHERE id = :id"), {"id": user_id})
    if not exists.fetchone():
        raise HTTPException(status_code=404, detail="使用者不存在")

    if req.role is not None:
        if req.role not in ("admin", "user"):
            raise HTTPException(status_code=400, detail="角色只能是 admin 或 user")
        await db.execute(text("UPDATE users SET account_level = :role WHERE id = :id"), {"role": req.role, "id": user_id})

    if req.group_name is not None:
        group = await db.execute(text("SELECT id FROM permission_groups WHERE name = :name"), {"name": req.group_name})
        group_row = group.fetchone()
        if not group_row:
            raise HTTPException(status_code=404, detail="找不到權限群組")
        # Upsert user_permissions
        await db.execute(text("""
            INSERT INTO user_permissions (user_id, group_id, section, workshop)
            VALUES (:uid, :gid, :section, :workshop)
            ON CONFLICT (user_id) DO UPDATE SET group_id = :gid
        """), {"uid": user_id, "gid": group_row.id, "section": req.section or "", "workshop": req.workshop or ""})
    elif req.section is not None or req.workshop is not None:
        await db.execute(text("""
            UPDATE user_permissions SET section = COALESCE(:section, section), workshop = COALESCE(:workshop, workshop)
            WHERE user_id = :uid
        """), {"uid": user_id, "section": req.section, "workshop": req.workshop})

    await db.commit()
    return {"success": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    """Delete a user and their permissions."""
    if user_id == admin.get("id"):
        raise HTTPException(status_code=400, detail="無法刪除自己的帳號")
    await db.execute(text("DELETE FROM user_permissions WHERE user_id = :id"), {"id": user_id})
    result = await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="使用者不存在")
    return {"success": True}


@router.get("/groups")
async def list_groups(db: AsyncSession = Depends(get_db), admin: dict = Depends(require_admin)):
    """List all permission groups."""
    result = await db.execute(text(
        "SELECT id, name, display_name, description FROM permission_groups ORDER BY name"
    ))
    groups = [
        {"id": r.id, "name": r.name, "display_name": r.display_name, "description": r.description}
        for r in result.fetchall()
    ]
    return {"groups": groups}
