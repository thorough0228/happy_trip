"""用户认证：密码哈希（pbkdf2）+ JWT 签发/验证。"""

from __future__ import annotations

import hashlib
import os
import secrets
import warnings
from typing import Optional

import jwt
from fastapi import HTTPException, Request, status

_SECRET: str | None = None


def _get_secret() -> str:
    global _SECRET
    if _SECRET is None:
        _SECRET = os.getenv("JWT_SECRET", "")
        if not _SECRET:
            _SECRET = secrets.token_hex(32)
            warnings.warn(
                "JWT_SECRET 未配置，已随机生成。重启后所有 token 失效，"
                "请在 .env 中设置 JWT_SECRET。",
                stacklevel=2,
            )
    return _SECRET


def hash_password(password: str) -> str:
    """返回 'salt:hex' 格式的哈希字符串。"""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, hex_hash = stored.split(":", 1)
    except ValueError:
        return False
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return secrets.compare_digest(h.hex(), hex_hash)


def create_token(user_id: str) -> str:
    return jwt.encode({"sub": user_id}, _get_secret(), algorithm="HS256")


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=["HS256"])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_user_id_from_request(request: Request) -> Optional[str]:
    """
    从请求头提取 user_id。未携带 token 或 token 无效时返回 None。
    """
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return decode_token(parts[1])


def require_user_id_from_request(request: Request) -> str:
    """从请求中提取 user_id，未登录则 401。"""
    user_id = get_user_id_from_request(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录",
        )
    return user_id
