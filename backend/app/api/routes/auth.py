"""用户认证路由：注册、登录。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.auth import create_token, hash_password, verify_password
from app.core.database import create_user, get_user_by_username

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register")
def register(username: str, password: str) -> dict:
    """用户注册。"""
    if not username or not username.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名不能为空",
        )
    if not password or len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码至少6个字符",
        )
    username = username.strip()

    existing = get_user_by_username(username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    password_hash = hash_password(password)
    user_id = create_user(username, password_hash)
    token = create_token(user_id)

    return {"user_id": user_id, "token": token, "username": username}


@router.post("/login")
def login(username: str, password: str) -> dict:
    """用户登录。"""
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    user = get_user_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not verify_password(password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    token = create_token(user["id"])
    return {"user_id": user["id"], "token": token, "username": user["username"]}
