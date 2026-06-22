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


class SavePromptIn(BaseModel):
    name: str = Field(..., min_length=1)
    text: str = Field(...)
    description: str | None = None


class GenerateReportIn(BaseModel):
    client_id: str = Field(..., min_length=1)
    report_type: str = Field("recommendations")


class CreateClientIn(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = Field(..., min_length=1)
    timezone: str = "Asia/Dubai"
    language: str = "ru"
    paid: bool = Field(...)                    # оплачено / не оплачено
    mode: str = Field("full")                  # 'basic' (базовый) | 'full' (полный)
    paid_until: str | None = None              # 'YYYY-MM-DD'; обязателен при paid=True


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


@app.get("/nutritionist/prompts")
def prompts_list(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> Dict[str, Any]:
    """Список доступных промптов {name: {source, ...}} — файлы + переопределения из БД."""
    from prompts import list_available_prompts

    return list_available_prompts()


@app.get("/nutritionist/prompt")
def prompt_load(
    name: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, str]:
    """Текущий текст промпта по имени (БД-приоритет → файл)."""
    from prompts import load_prompt

    try:
        return {"name": name, "text": load_prompt(name)}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/nutritionist/prompt")
def prompt_save(
    body: SavePromptIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, bool]:
    """Сохраняет промпт в БД (system_settings.prompts), приоритет над файлом."""
    from prompts import save_prompt

    try:
        save_prompt(body.name, body.text, description=body.description)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.get("/nutritionist/report-types")
def report_types(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> Dict[str, str]:
    """Доступные типы отчётов {report_type: title} — для выбора во фронте."""
    from agents.nutritionist.reports import list_report_types

    return list_report_types()


@app.post("/nutritionist/report")
def nutritionist_report(
    body: GenerateReportIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Формирует отчёт по клиенту (агент по шаблону). Сохранение/правку фронт делает в Supabase."""
    from agents.nutritionist.reports import generate_report

    try:
        return generate_report(body.client_id, body.report_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(
    body: CreateClientIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Создаёт аккаунт клиента (приглашение по email). Только для нутрициолога.

    Нутрициолог обязан задать стартовые статусы (оплата и режим). Без корректной
    оплаты клиент не сможет войти в кабинет (бизнес-правило check_web_access).
    """
    if "@" not in body.email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")

    if body.mode not in ("basic", "full"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="mode must be 'basic' or 'full'")

    if body.paid and not body.paid_until:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="paid_until is required when paid is true",
        )

    # Маппинг статусов: оплата → payment_status; режим → client_status (тариф из статуса).
    payment_status = "active" if body.paid else "inactive"
    client_status = "active" if body.mode == "full" else "onboarding"

    from database.auth import invite_client_account

    try:
        return invite_client_account(
            email=body.email,
            name=body.name,
            timezone=body.timezone,
            language=body.language,
            actor_user_id=user["user_id"],
            payment_status=payment_status,
            client_status=client_status,
            paid_until=body.paid_until if body.paid else None,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
