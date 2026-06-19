"""
FastAPI-приложение — API для веб-фронта.

Эндпоинты:
- GET  /health             — проверка живости (без авторизации)
- GET  /me                 — текущий пользователь (роль, client_id, статусы)
- POST /chat               — диалог клиента с агентом (роль client)
- POST /nutritionist/query — запрос нутрициолога к агенту (роль nutritionist)

CRUD/Auth/Storage фронт делает напрямую в Supabase под RLS. Здесь — только агент.
Запуск (Render/локально): uvicorn api.main:app --host 0.0.0.0 --port $PORT
"""

import os
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_role

app = FastAPI(title="Nutritionist Agent API", version="1.0")

# CORS: список origin фронта через переменную окружения (через запятую).
_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================================
# СХЕМЫ ЗАПРОСОВ
# ========================================

class ChatIn(BaseModel):
    message: str = Field(..., min_length=1)
    message_type: str = "text"  # text | photo | voice (vision/voice — позже, Фаза 2)


class NutritionistQueryIn(BaseModel):
    message: str = Field(..., min_length=1)


class CreateClientIn(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    timezone: str = "Asia/Dubai"
    language: str = "ru"


# ========================================
# ЭНДПОИНТЫ
# ========================================

@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/me")
def me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Текущий пользователь — для маршрутизации по роли и gate доступа во фронте."""
    return user


@app.post("/chat")
def chat(body: ChatIn, user: Dict[str, Any] = Depends(require_role("client"))) -> Dict[str, Any]:
    """Сообщение клиента агенту. client_id берётся из токена (не из тела)."""
    if not user.get("client_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client profile not found for this user",
        )

    # Ленивая загрузка: не тянем агентов при импорте приложения.
    from agents.router import route_to_client

    return route_to_client(
        client_id=user["client_id"],
        message=body.message,
        channel="web",
        message_type=body.message_type,
        metadata={},
    )


@app.post("/nutritionist/query")
def nutritionist_query(
    body: NutritionistQueryIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Запрос нутрициолога к агенту (аналитика/управление)."""
    from agents.router import route_to_nutritionist

    return route_to_nutritionist(
        nutritionist_id=user["user_id"],
        message=body.message,
        channel="web",
        message_type="text",
        metadata={},
    )


@app.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    body: CreateClientIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Создаёт аккаунт клиента (приглашение по email). Только для нутрициолога."""
    if "@" not in body.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")

    from database.auth import invite_client_account

    try:
        return invite_client_account(
            email=body.email,
            name=body.name,
            timezone=body.timezone,
            language=body.language,
            actor_user_id=user["user_id"],
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
