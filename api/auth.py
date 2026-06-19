"""
FastAPI-зависимости аутентификации.

get_current_user — извлекает Bearer-токен, валидирует через Supabase и резолвит
прикладного пользователя (роль + client_id) из БД.
require_role(...) — фабрика зависимости-гейта по роли.
"""

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, Header, HTTPException, status

from database.auth import authenticate


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """Возвращает прикладного пользователя по Bearer-токену или 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1].strip()
    user = authenticate(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or user not registered",
        )
    return user


def require_role(*roles: str) -> Callable[..., Dict[str, Any]]:
    """Зависимость-гейт: пропускает только пользователей с одной из указанных ролей."""

    def _dependency(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(roles)}",
            )
        return user

    return _dependency
