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
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_role


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл: Telegram-бот + планировщик уведомлений на старте, остановка на выходе."""
    from api.telegram_webhook import startup_telegram, shutdown_telegram
    from api.scheduler import start_scheduler, shutdown_scheduler

    await startup_telegram()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()
        await shutdown_telegram()


app = FastAPI(title="Nutritionist Agent API", version="1.0", lifespan=lifespan)

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


class SaveSettingIn(BaseModel):
    key: str = Field(..., min_length=1)
    value: Any = None  # произвольный JSON (список/объект/число/строка)


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


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> Dict[str, bool]:
    """Приём апдейтов Telegram (webhook). Без настроенного бота — 503."""
    from api.telegram_webhook import process_webhook_update, webhook_secret_ok

    if not webhook_secret_ok(x_telegram_bot_api_secret_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret token")

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    ok = await process_webhook_update(data)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Telegram bot not configured"
        )
    return {"ok": True}


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


@app.post("/nutritionist/setting")
def save_setting(
    body: SaveSettingIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, bool]:
    """
    Сохраняет настройку system_settings через бэкенд (upsert) + пишет audit_log.

    Раньше фронт писал настройки напрямую в Supabase (мимо аудита, разрыв №6).
    Теперь запись идёт здесь: фиксируем кто/что менял (old/new) под ролью нутрициолога.
    """
    from database import queries

    try:
        old_value = queries.get_setting(body.key)
        queries.upsert_system_setting(body.key, body.value, updated_by=user["user_id"])
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="update_setting",
            entity_type="settings",
            entity_id=body.key,
            old_value={"value": old_value},
            new_value={"value": body.value},
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


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


@app.get("/nutritionist/knowledge")
def knowledge_list(
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Список документов базы знаний нутрициолога."""
    from database import queries

    return {"documents": queries.list_knowledge_documents()}


@app.post("/nutritionist/knowledge")
async def knowledge_upload(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """
    Загружает труд/методичку в базу знаний (knowledge_base, pgvector).

    Файл принимается напрямую (multipart): извлекаем текст, режем на чанки,
    эмбеддим (ada-002) и пишем в knowledge_base. Оригинал в v1 не храним —
    для RAG нужны только чанки. Доступно знаниям всех агентов через поиск.
    """
    from database import queries
    from database.models import DocumentMetadata
    from utils.ingestion import extract_text, ingest_into_knowledge_base

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    try:
        text = extract_text(file_bytes, file.content_type or "", file.filename or "")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text extracted from document",
        )

    display = title or file.filename or "Документ"
    rows = queries.insert_document_metadata(
        DocumentMetadata(
            source="knowledge_base",
            document_type="knowledge",
            title=display,
            file_name=file.filename,
            mime_type=file.content_type,
            file_size_bytes=len(file_bytes),
        )
    )
    document_id = (rows or [{}])[0].get("id")
    if not document_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document metadata",
        )

    try:
        chunks = ingest_into_knowledge_base(document_id, text, source=display)
    except Exception as e:
        # Откатываем висячую запись метаданных, чтобы не плодить пустые документы.
        queries.delete_document_metadata(document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ingestion failed: {e}"
        )

    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=user["user_id"],
        action="add_knowledge",
        entity_type="knowledge_base",
        entity_id=document_id,
        new_value={"title": display, "file_name": file.filename, "chunks": chunks},
    )
    return {"document_id": document_id, "title": display, "chunks": chunks}


@app.delete("/nutritionist/knowledge/{document_id}")
def knowledge_delete(
    document_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, bool]:
    """Удаляет документ базы знаний и его чанки."""
    from database import queries

    doc = queries.get_document_metadata(document_id)
    if not doc or doc.get("source") != "knowledge_base":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge document not found")

    queries.delete_knowledge_base_chunks(document_id)
    queries.delete_document_metadata(document_id)
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=user["user_id"],
        action="delete_knowledge",
        entity_type="knowledge_base",
        entity_id=document_id,
    )
    return {"ok": True}


CLIENT_DOCS_BUCKET = "client-documents"


@app.post("/documents/{document_id}/ingest")
def ingest_client_document(
    document_id: str,
    user: Dict[str, Any] = Depends(require_role("client")),
) -> Dict[str, Any]:
    """
    Векторизует уже загруженный документ клиента в client_documents (pgvector).

    Фронт грузит файл напрямую в Storage и пишет document_metadata, затем зовёт
    этот эндпоинт. Контент берётся из Storage по storage_url, режется на чанки,
    эмбеддится (ada-002) и пишется под изоляцией client_id. Идемпотентно:
    старые чанки документа удаляются перед записью новых.
    """
    client_id = user.get("client_id")
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client profile not found for this user",
        )

    from database import queries
    from database.client import get_supabase_service_client
    from utils.ingestion import extract_text, ingest_into_client_documents

    doc = queries.get_document_metadata(document_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # Изоляция: документ должен принадлежать вызывающему клиенту.
    if str(doc.get("client_id")) != str(client_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your document")

    storage_path = doc.get("storage_url")
    if not storage_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Document has no storage_url"
        )

    # Скачивание из приватного бакета сервис-клиентом.
    try:
        sb = get_supabase_service_client()
        file_bytes = sb.storage.from_(CLIENT_DOCS_BUCKET).download(storage_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Storage download failed: {e}"
        )

    try:
        text = extract_text(file_bytes, doc.get("mime_type") or "", doc.get("file_name") or "")
    except ValueError as e:
        # Неподдерживаемый тип (например, скан-изображение без текстового слоя)
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e))

    if not text.strip():
        return {"document_id": document_id, "chunks": 0, "note": "no_text_extracted"}

    # Идемпотентность: переиндексация без дублей.
    queries.delete_client_document_chunks(document_id)

    try:
        chunks = ingest_into_client_documents(client_id, document_id, text)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ingestion failed: {e}"
        )

    # Best-effort: вытащить числовые показатели анализов в lab_results (source='client_pdf').
    # Сбой извлечения не должен ронять успешную векторизацию.
    labs_saved = 0
    try:
        from utils.labs import extract_labs_from_text

        for lab in extract_labs_from_text(text):
            queries.insert_lab_result(
                client_id=client_id,
                indicator=lab["indicator"],
                value=lab["value"],
                unit=lab.get("unit"),
                source="client_pdf",
                document_id=document_id,
            )
            labs_saved += 1
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"lab extraction from document failed: {e}")

    return {"document_id": document_id, "chunks": chunks, "labs": labs_saved}


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
