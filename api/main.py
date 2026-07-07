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
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.auth import get_current_user, require_role


def _configure_logging() -> None:
    """
    Настройка логирования веб-процесса (uvicorn сам корневой логгер не трогает → INFO
    из наших модулей по умолчанию подавляется на уровне WARNING). Поднимаем INFO для
    наших пакетов, сторонние библиотеки оставляем тихими (иначе httpx/supabase шумят).

    Это делает видимыми в Render наши info-диагностики (COVERAGE покрытия оркестратора,
    планировщик, failover LLM). Уровень наших модулей — LOG_LEVEL (по умолчанию INFO).
    """
    import logging

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=logging.WARNING)  # корень/3rd-party — тихо
    for name in ("agents", "api", "database", "utils", "business_rules", "monitoring"):
        logging.getLogger(name).setLevel(level)


_configure_logging()


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
    phone: str | None = None                   # необязательный телефон клиента
    timezone: str = "Asia/Dubai"
    language: str = "ru"
    paid: bool = Field(...)                    # оплачено / не оплачено
    mode: str = Field("full")                  # 'basic' (базовый) | 'full' (полный)
    paid_until: str | None = None              # 'YYYY-MM-DD'; обязателен при paid=True


class ClientStatusIn(BaseModel):
    client_status: str | None = None           # lead|onboarding|active|paused|completed|archived
    payment_status: str | None = None          # trial|active|inactive
    paid_until: str | None = None              # 'YYYY-MM-DD' | '' (сбросить)


class ReminderIn(BaseModel):
    title: str
    remind_at: str                             # 'HH:MM' локального времени клиента
    recurrence: str = "daily"                  # once|daily|weekly
    weekday: int | None = None                 # weekly: 0=Пн … 6=Вс
    remind_date: str | None = None             # once: 'YYYY-MM-DD'
    requires_response: bool = False            # ждём ответа клиента (контроль)
    expected_response: str | None = None       # ключ показателя | 'text' | None
    followup_after_hours: int | None = None    # переопределяет профиль кадэнса
    max_followups: int | None = None
    response_deadline: str | None = None       # 'HH:MM' дедлайн отчёта (еда: 12/17/22)


class ReminderPatchIn(BaseModel):
    title: str | None = None
    remind_at: str | None = None
    recurrence: str | None = None
    weekday: int | None = None
    remind_date: str | None = None
    requires_response: bool | None = None
    expected_response: str | None = None
    followup_after_hours: int | None = None
    max_followups: int | None = None
    response_deadline: str | None = None
    active: bool | None = None


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


class LlmTestIn(BaseModel):
    provider: str
    model: str


@app.get("/nutritionist/llm/providers")
def llm_providers(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> Dict[str, Any]:
    """Провайдеры: какие доступны (SDK/ключ) и все известные (нативные + кастом из реестра)."""
    from utils.llm import list_available_providers, get_custom_providers, NATIVE_PROVIDERS

    custom = list(get_custom_providers().keys())
    return {"available": list_available_providers(), "all": list(NATIVE_PROVIDERS) + custom}


@app.get("/nutritionist/llm/models")
def llm_models(
    provider: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Живой список chat/generate-моделей провайдера (ListModels, кэш 5 мин)."""
    from utils.llm import list_provider_models

    return {"provider": provider, "models": list_provider_models(provider)}


@app.post("/nutritionist/llm/test")
def llm_test(
    body: LlmTestIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Мини-пинг модели перед сохранением: {ok, latency_ms, model, error}."""
    from utils.llm import test_model

    return test_model(body.provider, body.model)


@app.get("/nutritionist/llm/defaults")
def llm_defaults(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> Dict[str, Any]:
    """Код-дефолты llm_config — для кнопки «Сбросить на дефолт» и подписи дефолта."""
    from utils.llm import build_default_llm_config

    return build_default_llm_config()


@app.get("/nutritionist/coverage")
def orchestrator_coverage(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> Dict[str, Any]:
    """
    Покрытие ходов LLM-оркестраторами (Ф3, наблюдаемость). Счётчики in-memory за время
    жизни процесса (сбрасываются на деплое/рестарте). Критерий чистки графа: за период
    graph_fallback == 0, доля orchestrator растёт к 100%.
    """
    from agents.core.coverage import snapshot

    counts = snapshot()

    def _rate(role: str) -> Optional[float]:
        total = sum(v for k, v in counts.items() if k.startswith(f"{role}:"))
        if not total:
            return None
        return round(counts.get(f"{role}:orchestrator", 0) / total, 3)

    return {
        "counts": counts,
        "orchestrator_rate": {"client": _rate("client"), "nutritionist": _rate("nutritionist")},
        "fallbacks": {
            "client": counts.get("client:graph_fallback", 0),
            "nutritionist": counts.get("nutritionist:graph_fallback", 0),
        },
    }


@app.get("/nutrition/daily")
def nutrition_daily(
    days: int = 14,
    client_id: Optional[str] = None,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Суточные тоталы питания (ккал/Б/Ж/У/сахар/вода) за период — для графиков питания.

    Клиент видит ТОЛЬКО свои данные (client_id из токена, query игнорируется); нутрициолог —
    любого клиента (client_id обязателен). targets — нормы из активного плана (целевые калории,
    норма воды) для линий-ориентиров на графике.
    """
    from database import queries

    role = user.get("role")
    if role == "client":
        cid = user.get("client_id")
        if not cid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Client profile not found for this user")
    elif role == "nutritionist":
        cid = client_id
        if not cid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="client_id is required")
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    days = max(1, min(int(days or 14), 90))
    series = queries.get_nutrition_daily(cid, days=days)

    targets: Dict[str, Any] = {}
    try:
        plan = queries.get_active_nutrition_plan(cid) or {}
        pj = plan.get("plan_json") if isinstance(plan.get("plan_json"), dict) else {}
        tc = (pj or {}).get("target_calories", plan.get("target_calories"))
        if tc:
            targets["kcal"] = tc
        wt = (pj or {}).get("water_ml_target")
        if wt:
            targets["water_ml"] = wt
    except Exception:  # noqa: BLE001 — нормы опциональны, график рисуется и без них
        pass

    return {"client_id": cid, "days": days, "series": series, "targets": targets}


@app.get("/nutritionist/prompts")
def prompts_list(user: Dict[str, Any] = Depends(require_role("nutritionist"))) -> List[Dict[str, Any]]:
    """
    Реестр промптов с понятными названиями, разделом и источником значения.

    Раздел communication — нутрициолог правит сам; system — только разработчик
    (на фронте показывается read-only). См. prompts/registry.py.
    """
    from prompts import list_prompts_with_meta

    return list_prompts_with_meta()


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
    """Сохраняет промпт в БД (system_settings.prompts), приоритет над файлом.

    Системные промпты (раздел system) — read-only через веб: их правит только
    разработчик в файлах. Попытка сохранить такой промпт → 403.
    """
    from prompts import save_prompt, is_editable

    if not is_editable(body.name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Этот промпт системный и редактируется только разработчиком (read-only).",
        )

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
            phone=(body.phone or "").strip() or None,
            timezone=body.timezone,
            language=body.language,
            actor_user_id=user["user_id"],
            payment_status=payment_status,
            client_status=client_status,
            paid_until=body.paid_until if body.paid else None,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


# Срок годности ссылки привязки Telegram (дней).
TELEGRAM_LINK_TTL_DAYS = 14


def _telegram_deep_link(token: str) -> str:
    """Собирает t.me/<bot>?start=<token> из TELEGRAM_BOT_USERNAME (или '' если не задан)."""
    username = (os.environ.get("TELEGRAM_BOT_USERNAME") or "").strip().lstrip("@")
    return f"https://t.me/{username}?start={token}" if username else ""


@app.post("/clients/{client_id}/status")
def update_client_status_endpoint(
    client_id: str,
    body: ClientStatusIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """
    Обновление статусов клиента нутрициологом (жизненный цикл + оплата + срок оплаты) с
    записью в audit_logs. Модель — 2 оси: client_status + payment_status/paid_until
    (access_status убран). paid_until авто-блокирует доступ при истечении (access_rules).
    """
    from database import queries

    old = queries.get_client_by_id(client_id)
    if not old:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    fields = {
        k: v for k, v in {
            "client_status": body.client_status,
            "payment_status": body.payment_status,
            "paid_until": body.paid_until,
        }.items() if v is not None
    }
    if not fields:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No status fields provided")

    try:
        queries.update_client_status(
            client_id=client_id,
            client_status=body.client_status,
            payment_status=body.payment_status,
            paid_until=body.paid_until,
        )
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="change_status",
            entity_type="client",
            entity_id=client_id,
            old_value={k: old.get(k) for k in fields},
            new_value=fields,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def _validate_reminder(recurrence: str, weekday, remind_date, remind_at: str | None) -> None:
    """Проверка полей напоминания. Кидает HTTPException 400 при ошибке."""
    if recurrence is not None and recurrence not in ("once", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="recurrence must be once|daily|weekly")
    if recurrence == "weekly" and weekday is None:
        raise HTTPException(status_code=400, detail="weekday required for weekly reminder")
    if weekday is not None and not (0 <= weekday <= 6):
        raise HTTPException(status_code=400, detail="weekday must be 0..6 (Mon..Sun)")
    if recurrence == "once" and not remind_date:
        raise HTTPException(status_code=400, detail="remind_date required for once reminder")
    if remind_at is not None and len(remind_at.split(":")) < 2:
        raise HTTPException(status_code=400, detail="remind_at must be 'HH:MM'")


@app.get("/clients/{client_id}/reminders")
def list_reminders_endpoint(
    client_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Список напоминаний клиента (для редактора в кабинете нутрициолога)."""
    from database import queries

    return {"reminders": queries.get_reminders_by_client(client_id)}


@app.post("/clients/{client_id}/reminders", status_code=status.HTTP_201_CREATED)
def create_reminder_endpoint(
    client_id: str,
    body: ReminderIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Создать напоминание клиенту (с аудитом)."""
    from database import queries

    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    _validate_reminder(body.recurrence, body.weekday, body.remind_date, body.remind_at)

    try:
        created = queries.create_reminder(
            client_id=client_id,
            title=title,
            remind_at=body.remind_at,
            recurrence=body.recurrence,
            weekday=body.weekday,
            remind_date=body.remind_date or None,
            requires_response=body.requires_response,
            expected_response=body.expected_response or None,
            followup_after_hours=body.followup_after_hours,
            max_followups=body.max_followups,
            response_deadline=body.response_deadline or None,
        )
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="create_reminder",
            entity_type="reminder",
            entity_id=(created or {}).get("id"),
            new_value={"client_id": client_id, "title": title, "remind_at": body.remind_at,
                       "recurrence": body.recurrence},
        )
        return {"reminder": created}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/clients/{client_id}/reminders/{reminder_id}")
def update_reminder_endpoint(
    client_id: str,
    reminder_id: str,
    body: ReminderPatchIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Обновить напоминание (partial). Пустое тело — 400."""
    from database import queries

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    _validate_reminder(
        updates.get("recurrence"), updates.get("weekday"),
        updates.get("remind_date"), updates.get("remind_at"),
    )

    try:
        updated = queries.update_reminder(reminder_id, updates)
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="update_reminder",
            entity_type="reminder",
            entity_id=reminder_id,
            new_value=updates,
        )
        return {"reminder": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/clients/{client_id}/reminders/{reminder_id}")
def delete_reminder_endpoint(
    client_id: str,
    reminder_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Удалить напоминание (срабатывания уйдут каскадом)."""
    from database import queries

    try:
        queries.delete_reminder(reminder_id)
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="delete_reminder",
            entity_type="reminder",
            entity_id=reminder_id,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ControlledMetricsIn(BaseModel):
    metrics: List[Dict[str, Any]]  # [{key,label_ru,label_en?,unit,category}]


@app.get("/clients/{client_id}/controlled-metrics")
def list_controlled_metrics_endpoint(
    client_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Каталог контролируемых показателей клиента (для пикера напоминаний + редактора)."""
    from database import queries

    return {"metrics": queries.get_controlled_metrics(client_id)}


@app.put("/clients/{client_id}/controlled-metrics")
def set_controlled_metrics_endpoint(
    client_id: str,
    body: ControlledMetricsIn,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Перезаписать каталог контролируемых показателей клиента (с аудитом)."""
    from database import queries

    # Нормализуем категорию по ключу (physical/sleep/custom), чтобы запись роутилась верно.
    from agents.client.intake_store import metric_category

    metrics = []
    for m in body.metrics:
        key = str(m.get("key") or "").strip()
        if not key:
            continue
        metrics.append({
            "key": key,
            "label_ru": m.get("label_ru") or key,
            "label_en": m.get("label_en") or m.get("label_ru") or key,
            "unit": m.get("unit") or "",
            "category": metric_category(key),
        })
    try:
        queries.set_controlled_metrics(client_id, metrics)
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=user["user_id"],
            action="set_controlled_metrics",
            entity_type="profile",
            entity_id=client_id,
            new_value={"count": len(metrics)},
        )
        return {"metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clients/{client_id}/telegram-link")
def create_telegram_link(
    client_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Создаёт (перевыпускает) одноразовую ссылку привязки Telegram для клиента.

    Старый токен затирается (прежняя ссылка перестаёт работать). Ссылку нутрициолог
    отправляет клиенту; клиент кликает → бот привязывает его telegram_id.
    """
    from database import queries

    client = queries.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    token = secrets.token_urlsafe(24)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=TELEGRAM_LINK_TTL_DAYS)
    ).isoformat()
    queries.set_client_link_token(client_id, token, expires_at)
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=user.get("user_id"),
        action="create_telegram_link",
        entity_type="client",
        entity_id=client_id,
        new_value={"expires_at": expires_at},
    )

    deep_link = _telegram_deep_link(token)
    return {
        "token": token,
        "deep_link": deep_link,
        "expires_at": expires_at,
        "configured": bool(deep_link),
    }


@app.delete("/clients/{client_id}/telegram-link")
def delete_telegram_link(
    client_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """Отвязывает Telegram от клиента (обнуляет telegram_id и активный токен).

    Используется, если по ссылке привязался не тот человек: отвязать → создать новую ссылку.
    """
    from database import queries

    client = queries.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    queries.unlink_client_telegram(client_id)
    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=user.get("user_id"),
        action="unlink_telegram",
        entity_type="client",
        entity_id=client_id,
        old_value={"telegram_id": client.get("telegram_id")},
    )
    return {"ok": True}


@app.post("/clients/{client_id}/reset-password")
def reset_client_password(
    client_id: str,
    user: Dict[str, Any] = Depends(require_role("nutritionist")),
) -> Dict[str, Any]:
    """
    Сброс пароля клиента нутрициологом (обход почты клиента: без домена Supabase/Brevo не шлют).

    Генерирует временный пароль, ставит его клиенту через GoTrue admin (email_confirm),
    возвращает пароль в ответе (кабинет покажет/скопирует) и best-effort дублирует письмом
    нутрициологу на его почту (Gmail SMTP). Сам пароль в аудит НЕ пишется.
    """
    from database import auth as db_auth
    from database import queries
    from utils import mailer

    client = queries.get_client_by_id(client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")

    auth_id = queries.get_user_auth_id(client.get("user_id"))
    if not auth_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У клиента нет связанного Auth-аккаунта",
        )

    new_password = secrets.token_urlsafe(9)

    try:
        db_auth.set_user_password(auth_id, new_password)
    except Exception as e:  # noqa: BLE001 — пробрасываем как 502 с причиной
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    # Письмо нутрициологу — best-effort, в обход Supabase/Brevo.
    nutri_email = os.environ.get("GMAIL_USER") or user.get("email") or ""
    client_label = client.get("name") or client.get("email") or client_id
    email_result = mailer.send_email(
        to=nutri_email,
        subject=f"Сброс пароля клиента: {client_label}",
        body=(
            f"Временный пароль для клиента {client.get('name') or ''} "
            f"({client.get('email') or 'без email'}):\n\n"
            f"    {new_password}\n\n"
            f"Передайте его клиенту. После входа клиент может сменить пароль в кабинете."
        ),
    )

    queries.write_audit_log(
        actor_type="nutritionist",
        actor_id=user.get("user_id"),
        action="reset_client_password",
        entity_type="client",
        entity_id=client_id,
        new_value={"email_sent": email_result.get("sent")},
    )

    return {
        "password": new_password,
        "client_email": client.get("email"),
        "email_sent": bool(email_result.get("sent")),
        "email_reason": email_result.get("reason", ""),
        "sent_to": nutri_email if email_result.get("sent") else "",
    }
