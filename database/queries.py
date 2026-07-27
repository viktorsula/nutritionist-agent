import os
from typing import Any, Dict, List, Optional

from postgrest.exceptions import APIError

from .client import get_supabase_service_client
from .models import (
    AuditLog,
    Client,
    ClientDocumentChunk,
    ClientEvent,
    ClientProfile,
    Conversation,
    DocumentMetadata,
    KnowledgeBaseChunk,
    NutritionPlan,
    SystemSetting,
    Task,
    User,
    WellnessPlan,
)


def _service_client():
    return get_supabase_service_client()


def _extract_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _execute_single(request: Any) -> Any:
    try:
        response = request.execute()
        return _extract_data(response)
    except APIError as err:
        payload = err.args[0] if err.args else None
        if isinstance(payload, str) and "PGRST116" in payload:
            return None
        if isinstance(payload, dict) and payload.get("code") == "PGRST116":
            return None
        raise


def _execute_one(request: Any) -> Optional[Dict[str, Any]]:
    """Выполнить запрос и вернуть ПЕРВУЮ строку из data (или None).

    Для update/insert/upsert-цепочек нельзя вызывать `.single()`: на проде
    `supabase==2.10.0` билдер `.update().eq()` — это `SyncFilterRequestBuilder`
    без метода `.single()` (локальная 2.31 это маскировала → пути молча падали).
    Поэтому запрос идёт БЕЗ `.single()`, а первую строку из списка берём сами.
    """
    response = request.execute()
    data = _extract_data(response)
    if isinstance(data, list):
        return data[0] if data else None
    return data


def insert_document_metadata(metadata: DocumentMetadata) -> Any:
    supabase = _service_client()
    payload: Dict[str, Any] = {
        "source": metadata.source,
        "external_id": metadata.external_id,
        "client_id": str(metadata.client_id) if metadata.client_id else None,
        "document_type": metadata.document_type,
        "title": metadata.title,
        "description": metadata.description,
        "mime_type": metadata.mime_type,
        "storage_url": metadata.storage_url,
        "file_name": metadata.file_name,
        "file_size_bytes": metadata.file_size_bytes,
        "extracted_text": metadata.extracted_text,
        "metadata": metadata.metadata,
    }
    return _extract_data(
        supabase.table("document_metadata").insert(payload).execute()
    )


def get_document_metadata(document_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("document_metadata").select("*").eq("id", document_id).single()
    )


def delete_document_metadata(document_id: str) -> None:
    """Удаляет строку document_metadata (после удаления её чанков)."""
    supabase = _service_client()
    supabase.table("document_metadata").delete().eq("id", document_id).execute()


def list_knowledge_documents() -> List[Dict[str, Any]]:
    """Документы базы знаний нутрициолога (source='knowledge_base'), свежие сверху."""
    supabase = _service_client()
    response = (
        supabase.table("document_metadata")
        .select("id,title,file_name,mime_type,file_size_bytes,created_at")
        .eq("source", "knowledge_base")
        .order("created_at", desc=True)
        .execute()
    )
    return _extract_data(response) or []


def delete_knowledge_base_chunks(document_id: str) -> None:
    """Удаляет все чанки документа базы знаний (для переиндексации/удаления)."""
    supabase = _service_client()
    supabase.table("knowledge_base").delete().eq("document_id", document_id).execute()


def insert_knowledge_base_chunk(chunk: KnowledgeBaseChunk) -> Any:
    supabase = _service_client()
    payload = {
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": _vector_literal(chunk.embedding),
        "source": chunk.source,
    }
    return _extract_data(
        supabase.table("knowledge_base").insert(payload).execute()
    )


def insert_client_document_chunk(chunk: ClientDocumentChunk) -> Any:
    supabase = _service_client()
    payload = {
        "client_id": str(chunk.client_id),
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": _vector_literal(chunk.embedding),
    }
    return _extract_data(
        supabase.table("client_documents").insert(payload).execute()
    )


def get_client_by_id(client_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients").select("*").eq("id", client_id).single()
    )


def get_client_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients").select("*").eq("telegram_id", telegram_id).single()
    )


def _user_info_from_client(client: Dict[str, Any]) -> Dict[str, Any]:
    """Нормализует строку clients к контракту router.get_user_info (роль client)."""
    return {
        "id": client.get("id"),
        "role": "client",
        "name": client.get("name"),
        "telegram_id": client.get("telegram_id"),
        "email": client.get("email"),
    }


def get_nutritionist_user() -> Optional[Dict[str, Any]]:
    """
    Возвращает пользователя-нутрициолога (в v1.0 он один) из таблицы users.

    Нормализованный dict {id=user_id, role='nutritionist', name=None, email} или None.
    Используется для распознавания нутрициолога в Telegram (его telegram_id не в clients).
    """
    supabase = _service_client()
    rows = _extract_data(
        supabase.table("users").select("*").eq("role", "nutritionist").limit(1).execute()
    )
    user = rows[0] if rows else None
    if not user:
        return None
    return {
        "id": user.get("id"),
        "role": "nutritionist",
        "name": None,
        "email": user.get("email"),
    }


def get_user_auth_id(user_id: str) -> Optional[str]:
    """Возвращает Supabase Auth UUID (users.auth_id) по users.id или None."""
    if not user_id:
        return None
    supabase = _service_client()
    row = _execute_single(
        supabase.table("users").select("auth_id").eq("id", user_id).single()
    )
    return row.get("auth_id") if row else None


def get_user_by_telegram_id(telegram_id: Any) -> Optional[Dict[str, Any]]:
    """
    Резолвит пользователя по Telegram ID для router.get_user_info.

    Нутрициолог распознаётся по NUTRITIONIST_TELEGRAM_ID (его telegram_id не хранится
    в clients) → роль 'nutritionist', полноценный диалог с агентом через Telegram, как в вебе.
    Иначе — поиск среди клиентов (telegram_id в clients, BIGINT). Возвращает нормализованный
    dict {id, role, name, telegram_id?, email} или None.
    """
    try:
        tg_id = int(telegram_id)
    except (TypeError, ValueError):
        return None

    nutri_tg = (os.environ.get("NUTRITIONIST_TELEGRAM_ID") or "").strip()
    if nutri_tg and str(tg_id) == nutri_tg:
        nutri = get_nutritionist_user()
        if nutri:
            return nutri

    client = get_client_by_telegram_id(tg_id)
    return _user_info_from_client(client) if client else None


# =============================================
# ПРИВЯЗКА TELEGRAM (самопривязка по одноразовому токену, Вариант B)
# =============================================


def set_client_link_token(
    client_id: str, token: str, expires_at: Optional[str]
) -> Optional[Dict[str, Any]]:
    """
    Записывает (перевыпускает) одноразовый токен привязки Telegram клиенту.

    expires_at — ISO-8601 строка (UTC) или None. Перезапись затирает прежний токен —
    старая ссылка перестаёт работать.
    """
    supabase = _service_client()
    return _extract_data(
        supabase.table("clients")
        .update(
            {
                "telegram_link_token": token,
                "telegram_link_token_expires_at": expires_at,
            }
        )
        .eq("id", client_id)
        .execute()
    )


def get_client_by_link_token(token: str) -> Optional[Dict[str, Any]]:
    """Возвращает строку clients по токену привязки (или None). Срок годности проверяет вызывающий."""
    if not token:
        return None
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients")
        .select("*")
        .eq("telegram_link_token", token)
        .single()
    )


def link_client_telegram(client_id: str, telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Привязывает Telegram-аккаунт к клиенту: ставит telegram_id и ГАСИТ токен
    (одноразовость) вместе со сроком годности.
    """
    supabase = _service_client()
    return _extract_data(
        supabase.table("clients")
        .update(
            {
                "telegram_id": telegram_id,
                "telegram_link_token": None,
                "telegram_link_token_expires_at": None,
            }
        )
        .eq("id", client_id)
        .execute()
    )


def unlink_client_telegram(client_id: str) -> Optional[Dict[str, Any]]:
    """
    Отвязывает Telegram от клиента: обнуляет telegram_id и любой активный токен.
    После этого посторонний (если случайно привязался) теряет доступ в боте.
    """
    supabase = _service_client()
    return _extract_data(
        supabase.table("clients")
        .update(
            {
                "telegram_id": None,
                "telegram_link_token": None,
                "telegram_link_token_expires_at": None,
            }
        )
        .eq("id", client_id)
        .execute()
    )


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Резолвит пользователя по UUID для router.get_user_info (fallback после telegram).

    Сначала пробуем clients.id (роль client, id = client_id для оркестратора).
    Если не нашли — users.id (нутрициолог/observer, id = user_id). У таблицы users
    нет имени — имя живёт в clients, поэтому для них name=None. None если не найден.
    """
    if not user_id:
        return None

    # 1. Клиент по clients.id
    client = get_client_by_id(user_id)
    if client:
        return _user_info_from_client(client)

    # 2. Пользователь по users.id (нутрициолог/observer)
    supabase = _service_client()
    user = _execute_single(
        supabase.table("users").select("*").eq("id", user_id).single()
    )
    if not user:
        return None
    return {
        "id": user.get("id"),
        "role": user.get("role"),
        "name": None,
        "email": user.get("email"),
    }


def get_active_nutrition_plan(client_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("nutrition_plans")
        .select("*")
        .eq("client_id", client_id)
        .eq("is_active", True)
        .single()
    )


def get_tasks_by_client(client_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("tasks").select("*").eq("client_id", client_id).execute()
    )
    return _extract_data(response) or []


def get_latest_measurement(client_id: str) -> Optional[Dict[str, Any]]:
    """Последний замер тела клиента (вес/объёмы) из measurements (миграция 003)."""
    supabase = _service_client()
    response = (
        supabase.table("measurements")
        .select("*")
        .eq("client_id", client_id)
        .order("measured_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = _extract_data(response) or []
    return rows[0] if rows else None


def get_recent_measurements(client_id: str, limit: int = 2) -> List[Dict[str, Any]]:
    """Последние замеры клиента (свежие сверху, по времени записи) — для динамики/алерта веса."""
    supabase = _service_client()
    response = (
        supabase.table("measurements")
        .select("*")
        .eq("client_id", client_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _extract_data(response) or []


def insert_measurement(
    client_id: str,
    weight: Optional[float] = None,
    measured_at: Optional[str] = None,
    neck: Optional[float] = None,
    waist: Optional[float] = None,
    hips: Optional[float] = None,
    chest: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Добавляет замер тела клиента (вес/объёмы) в measurements. measured_at → сегодня по умолчанию."""
    supabase = _service_client()
    payload: Dict[str, Any] = {"client_id": client_id}
    for key, value in (
        ("weight", weight),
        ("measured_at", measured_at),
        ("neck", neck),
        ("waist", waist),
        ("hips", hips),
        ("chest", chest),
        ("notes", notes),
    ):
        if value is not None:
            payload[key] = value
    rows = _extract_data(
        supabase.table("measurements").insert(payload).execute()
    )
    return (rows or [None])[0]


# ── Контролируемые показатели (client_metrics, миграция 014) ──────────────────


def insert_client_metric(
    client_id: str,
    metric_key: str,
    category: Optional[str] = None,
    value_num: Optional[float] = None,
    value_text: Optional[str] = None,
    unit: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
    measured_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Записать значение контролируемого показателя (sleep/custom) в client_metrics."""
    supabase = _service_client()
    data: Dict[str, Any] = {"client_id": client_id, "metric_key": metric_key}
    for key, value in (
        ("category", category), ("value_num", value_num), ("value_text", value_text),
        ("unit", unit), ("meta", meta), ("measured_at", measured_at),
    ):
        if value is not None:
            data[key] = value
    return _execute_one(supabase.table("client_metrics").insert(data))


def get_client_metrics(
    client_id: str,
    metric_key: Optional[str] = None,
    since: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Значения контролируемых показателей клиента (свежие сверху). Фильтры по ключу/дате."""
    supabase = _service_client()
    query = supabase.table("client_metrics").select("*").eq("client_id", client_id)
    if metric_key:
        query = query.eq("metric_key", metric_key)
    if since:
        query = query.gte("measured_at", since)
    query = query.order("measured_at", desc=True).limit(limit)
    return _extract_data(query.execute()) or []


def get_controlled_metrics(client_id: str) -> List[Dict[str, Any]]:
    """Каталог контролируемых показателей клиента (client_profiles.controlled_metrics)."""
    supabase = _service_client()
    row = _execute_single(
        supabase.table("client_profiles").select("controlled_metrics").eq("client_id", client_id).single()
    )
    return (row or {}).get("controlled_metrics") or []


def set_controlled_metrics(client_id: str, metrics: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Перезаписать каталог контролируемых показателей клиента."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("client_profiles").update({"controlled_metrics": metrics}).eq("client_id", client_id)
    )


def get_recent_lab_results(client_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Недавние числовые анализы клиента из lab_results (миграция 003),
    свежие сверху. Для контекста ассистента (вес/холестерин и пр.).
    """
    supabase = _service_client()
    response = (
        supabase.table("lab_results")
        .select("indicator,value,unit,measured_at,source")
        .eq("client_id", client_id)
        .order("measured_at", desc=True)
        .limit(limit)
        .execute()
    )
    return _extract_data(response) or []


def insert_lab_result(
    client_id: str,
    indicator: str,
    value: Optional[float] = None,
    unit: Optional[str] = None,
    source: str = "client",
    measured_at: Optional[str] = None,
    document_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Добавляет числовой показатель анализа в lab_results. measured_at → сегодня по умолчанию."""
    supabase = _service_client()
    payload: Dict[str, Any] = {"client_id": client_id, "indicator": indicator, "source": source}
    for key, val in (
        ("value", value),
        ("unit", unit),
        ("measured_at", measured_at),
        ("document_id", document_id),
    ):
        if val is not None:
            payload[key] = val
    rows = _extract_data(
        supabase.table("lab_results").insert(payload).execute()
    )
    return (rows or [None])[0]


def get_system_setting(key: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("system_settings").select("*").eq("key", key).single()
    )


def get_all_system_settings() -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = supabase.table("system_settings").select("*").execute()
    return _extract_data(response) or []


def get_setting(key: str) -> Optional[Any]:
    """
    Получает значение настройки из system_settings.

    Используется для:
    - llm_config (конфигурация LLM моделей)
    - alert_thresholds (пороги алертов)
    - и других системных настроек

    Args:
        key: Ключ настройки (например, 'llm_config')

    Returns:
        Значение колонки `value` (может быть dict, list, str, int, bool)
        или None если настройка не найдена

    Example:
        >>> llm_config = get_setting('llm_config')
        >>> if llm_config and 'dialog' in llm_config:
        >>>     print(llm_config['dialog'])
    """
    setting = get_system_setting(key)
    if setting and isinstance(setting, dict):
        # Колонка JSONB называется 'value' (schema.sql); раньше тут было ошибочное
        # 'setting_value' → get_setting всегда возвращал None, и БД-переопределение
        # моделей/промптов/trusted_sources было мёртвым (маскировалось дефолтами/файлами).
        return setting.get('value')
    return None


def get_knowledge_base_chunks(document_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("knowledge_base")
        .select("*")
        .eq("document_id", document_id)
        .execute()
    )
    return _extract_data(response) or []


def get_client_document_chunks(client_id: str) -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = (
        supabase.table("client_documents")
        .select("*")
        .eq("client_id", client_id)
        .execute()
    )
    return _extract_data(response) or []


def delete_client_document_chunks(document_id: str) -> None:
    """Удаляет все чанки документа (для идемпотентной переиндексации)."""
    supabase = _service_client()
    supabase.table("client_documents").delete().eq("document_id", document_id).execute()


def _vector_literal(embedding: List[float]) -> str:
    """
    Преобразует список float в pgvector-литерал '[0.1,0.2,...]'.

    Через PostgREST RPC параметр vector(1536) НЕ принимает JSON-массив (Python list):
    PostgreSQL не кастует json[] → vector автоматически. pgvector принимает текстовый
    формат '[...]', который корректно кастуется к vector. Поэтому шлём строку.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def search_knowledge_base(
    query_embedding: List[float],
    match_count: int = 5,
    similarity_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """Семантический поиск по базе знаний нутрициолога (pgvector, cosine).

    Вызывает RPC match_knowledge_base (миграция 002_add_vector_search.sql).
    query_embedding — вектор длины 1536 (OpenAI ada-002), считается в utils/knowledge.py.
    Возвращает список чанков с полем similarity (0..1), отсортированный по убыванию близости.
    """
    supabase = _service_client()
    response = supabase.rpc(
        "match_knowledge_base",
        {
            "query_embedding": _vector_literal(query_embedding),
            "match_count": match_count,
            "similarity_threshold": similarity_threshold,
        },
    ).execute()
    return _extract_data(response) or []


def search_client_documents(
    query_embedding: List[float],
    client_id: str,
    match_count: int = 5,
    similarity_threshold: float = 0.0,
) -> List[Dict[str, Any]]:
    """Семантический поиск по документам конкретного клиента (pgvector, cosine).

    Вызывает RPC match_client_documents (миграция 002_add_vector_search.sql).
    Изоляция по client_id выполняется на уровне БД.
    """
    supabase = _service_client()
    response = supabase.rpc(
        "match_client_documents",
        {
            "query_embedding": _vector_literal(query_embedding),
            "p_client_id": str(client_id),
            "match_count": match_count,
            "similarity_threshold": similarity_threshold,
        },
    ).execute()
    return _extract_data(response) or []


# =============================================
# ФУНКЦИИ ДЛЯ BUSINESS_RULES
# =============================================


def get_client_profile(client_id: str) -> Optional[Dict[str, Any]]:
    """Получить медицинский профиль клиента (аллергии, пороги алертов)."""
    supabase = _service_client()
    return _execute_single(
        supabase.table("client_profiles").select("*").eq("client_id", client_id).single()
    )


def set_questionnaire_summary(client_id: str, summary: str) -> Optional[Dict[str, Any]]:
    """Сохранить компактное LLM-саммари анкеты (миграция 017)."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("client_profiles").update({"questionnaire_summary": summary}).eq("client_id", client_id)
    )


def insert_questionnaire_history(client_id: str, questionnaire_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Снимок ответов анкеты при отправке (первичной/повторной) — append-only (миграция 017)."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("client_questionnaire_history").insert(
            {"client_id": client_id, "questionnaire_json": questionnaire_json}
        )
    )


def get_questionnaire_history(client_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """История версий анкеты клиента, свежие сверху (для просмотра нутрициологом)."""
    supabase = _service_client()
    return _extract_data(
        supabase.table("client_questionnaire_history")
        .select("id,questionnaire_json,submitted_at")
        .eq("client_id", client_id)
        .order("submitted_at", desc=True)
        .limit(limit)
        .execute()
    ) or []


def insert_client_consent(
    client_id: str,
    consent_version: str,
    health_data: bool,
    telegram_channel: bool,
    channel: str = "web",
) -> Optional[Dict[str, Any]]:
    """Запись факта согласия клиента (LEGAL-1/LEGAL-5, миграция 018) — append-only."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("client_consents").insert({
            "client_id": client_id,
            "consent_version": consent_version,
            "health_data": health_data,
            "telegram_channel": telegram_channel,
            "channel": channel,
        })
    )


def get_latest_client_consent(client_id: str) -> Optional[Dict[str, Any]]:
    """Последнее согласие клиента (для сверки версии на бэкенде при необходимости)."""
    supabase = _service_client()
    rows = _extract_data(
        supabase.table("client_consents")
        .select("consent_version,accepted_at")
        .eq("client_id", client_id)
        .order("accepted_at", desc=True)
        .limit(1)
        .execute()
    ) or []
    return rows[0] if rows else None


def update_client(client_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Обновить профиль клиента (payment_status, access_status, client_status и др.)."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("clients")
        .update(updates)
        .eq("id", client_id)
    )


def update_client_status(
    client_id: str,
    client_status: Optional[str] = None,
    payment_status: Optional[str] = None,
    access_status: Optional[str] = None,
    paid_until: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Обновить статусы клиента (client_status/payment_status/paid_until; access_status — legacy)."""
    updates = {}
    if client_status is not None:
        updates["client_status"] = client_status
    if payment_status is not None:
        updates["payment_status"] = payment_status
    if access_status is not None:
        updates["access_status"] = access_status
    if paid_until is not None:
        updates["paid_until"] = paid_until or None

    if not updates:
        return None

    return update_client(client_id, updates)


def log_client_event(
    client_id: str,
    event_type: str,
    severity: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Записать событие клиента (алерты, действия)."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "event_type": event_type,
        "severity": severity,
        "payload_json": payload or {},
    }
    return _extract_data(
        supabase.table("client_events").insert(data).execute()
    )


def get_recent_alert_events(minutes: int = 5) -> List[Dict[str, Any]]:
    """
    Свежие события-алерты за последние N минут — для пуша нутрициологу в Telegram.

    Берём severity high/critical ИЛИ event_type IN (bad_wellbeing, meal_not_reported,
    questionnaire_updated) — эти типы важны для нутрициолога независимо от severity
    (questionnaire_updated — гарантированное уведомление об изменении анкеты, решение
    владельца: "нутрициолог обязательно узнает об изменении").
    Джойним имя клиента. Дедупликация по event.id — на стороне планировщика.
    """
    from datetime import datetime, timedelta

    supabase = _service_client()
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    return _extract_data(
        supabase.table("client_events")
        .select("id, client_id, event_type, severity, event_date, payload_json, clients(name)")
        .gte("event_date", since)
        .or_("severity.in.(high,critical),event_type.in.(bad_wellbeing,meal_not_reported,questionnaire_updated)")
        .order("event_date", desc=True)
        .execute()
    ) or []


def get_client_events(
    client_id: str,
    severity: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Получить события клиента, опционально фильтр по severity и/или event_type."""
    supabase = _service_client()
    query = (
        supabase.table("client_events")
        .select("*")
        .eq("client_id", client_id)
        .order("event_date", desc=True)
        .limit(limit)
    )

    if severity:
        query = query.eq("severity", severity)
    if event_type:
        query = query.eq("event_type", event_type)

    response = query.execute()
    return _extract_data(response) or []


def has_event_today(client_id: str, event_type: str, day: str) -> bool:
    """
    Есть ли у клиента событие данного типа за указанный день ('YYYY-MM-DD', UTC).

    Персистентная (в БД, не в памяти процесса) защита от повторных алертов одного дня —
    раньше дедуп no_response держался только в in-memory set (api/scheduler.py), который
    обнулялся при каждом рестарте бэкенда (деплой), из-за чего клиент получал по несколько
    алертов «нет ответа» за один день вместо одного.
    """
    supabase = _service_client()
    response = (
        supabase.table("client_events")
        .select("id")
        .eq("client_id", client_id)
        .eq("event_type", event_type)
        .gte("event_date", f"{day}T00:00:00")
        .lt("event_date", f"{day}T23:59:59.999999")
        .limit(1)
        .execute()
    )
    return bool(_extract_data(response))


def get_nutrition_daily(client_id: str, days: int = 14) -> List[Dict[str, Any]]:
    """
    Суточные тоталы питания за N дней из client_events (для графиков питания в кабинете).

    Суммирует по дням (по дате события):
    - calories_logged → payload_json.total: kcal / protein_g / fat_g / carb_g / sugar_g;
    - water_logged    → payload_json.water_ml.

    Ключи total канонизированы normalize()/kbju_from_legacy при записи. Возвращает список
    {date 'YYYY-MM-DD', kcal, protein_g, fat_g, carb_g, sugar_g, water_ml} по возрастанию даты.
    Дни без данных не включаются (фронт достроит ось при необходимости).
    """
    from datetime import datetime, timedelta

    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    supabase = _service_client()
    rows = _extract_data(
        supabase.table("client_events")
        .select("event_type, event_date, payload_json")
        .eq("client_id", client_id)
        .in_("event_type", ["calories_logged", "water_logged"])
        .gte("event_date", since)
        .order("event_date", desc=False)
        .execute()
    ) or []

    daily: Dict[str, Dict[str, Any]] = {}

    def _num(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def _day(d: str) -> Dict[str, Any]:
        return daily.setdefault(d, {
            "date": d, "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
            "carb_g": 0.0, "sugar_g": 0.0, "water_ml": 0.0,
        })

    for ev in rows:
        ed = (ev.get("event_date") or "")[:10]  # YYYY-MM-DD
        if not ed:
            continue
        payload = ev.get("payload_json") or {}
        etype = ev.get("event_type")
        if etype == "calories_logged":
            total = payload.get("total")
            if isinstance(total, dict):
                b = _day(ed)
                for k in ("kcal", "protein_g", "fat_g", "carb_g", "sugar_g"):
                    b[k] += _num(total.get(k))
        elif etype == "water_logged":
            _day(ed)["water_ml"] += _num(payload.get("water_ml"))

    return [daily[d] for d in sorted(daily)]


def update_system_setting(key: str, value: Any, updated_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Обновить системную настройку."""
    supabase = _service_client()

    updates = {
        "value": value,
    }
    if updated_by:
        updates["updated_by"] = updated_by

    return _execute_one(
        supabase.table("system_settings")
        .update(updates)
        .eq("key", key)
    )


def upsert_system_setting(key: str, value: Any, updated_by: Optional[str] = None) -> Any:
    """Создать/обновить настройку (upsert по key) — для записи с фронта через бэкенд."""
    from datetime import datetime

    supabase = _service_client()
    row = {
        "key": key,
        "value": value,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if updated_by:
        row["updated_by"] = updated_by

    return _extract_data(
        supabase.table("system_settings").upsert(row, on_conflict="key").execute()
    )


# =============================================
# ФУНКЦИИ ДЛЯ AGENTS
# =============================================


def save_conversation(
    client_id: str,
    role: str,
    message_text: str,
    channel: str = "telegram",
    conversation_type: str = "client_dialog",
    thread_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Сохранить сообщение в диалог."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "role": role,
        "message_text": message_text,
        "channel": channel,
        "conversation_type": conversation_type,
        "thread_id": thread_id,
        "metadata_json": metadata or {},
    }
    return _extract_data(
        supabase.table("conversations").insert(data).execute()
    )


def get_conversations(
    client_id: str,
    limit: int = 50,
    conversation_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Получить историю диалогов клиента."""
    supabase = _service_client()
    query = (
        supabase.table("conversations")
        .select("*")
        .eq("client_id", client_id)
        .order("message_timestamp", desc=True)
        .limit(limit)
    )

    if conversation_type:
        query = query.eq("conversation_type", conversation_type)

    response = query.execute()
    return _extract_data(response) or []


def count_client_dialog_messages(client_id: str) -> int:
    """Количество реплик клиентского диалога (conversation_type='client_dialog')."""
    supabase = _service_client()
    response = (
        supabase.table("conversations")
        .select("id", count="exact")
        .eq("client_id", client_id)
        .eq("conversation_type", "client_dialog")
        .execute()
    )
    return getattr(response, "count", 0) or 0


def update_conversation_summary(
    client_id: str, summary: str, message_count: int
) -> Optional[Dict[str, Any]]:
    """Сохраняет скользящую сводку диалога и маркер числа отражённых сообщений (миграция 009)."""
    from datetime import datetime

    supabase = _service_client()
    return _execute_one(
        supabase.table("clients")
        .update(
            {
                "conversation_summary": summary,
                "summary_message_count": message_count,
                "summary_updated_at": datetime.utcnow().isoformat(),
            }
        )
        .eq("id", client_id)
    )


def get_conversation_thread(thread_id: str) -> List[Dict[str, Any]]:
    """Получить все сообщения из thread (для контекста)."""
    supabase = _service_client()
    response = (
        supabase.table("conversations")
        .select("*")
        .eq("thread_id", thread_id)
        .order("message_timestamp", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def create_nutrition_plan(
    client_id: str,
    title: str,
    created_by: str,
    effective_from: str,
    plan_json: Optional[Dict[str, Any]] = None,
    supplements_json: Optional[Dict[str, Any]] = None,
    effective_to: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Создать план питания (триггер автоматически установит version и деактивирует старый)."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "title": title,
        "created_by": created_by,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "plan_json": plan_json or {},
        "supplements_json": supplements_json or {},
        "is_active": True,
    }
    return _extract_data(
        supabase.table("nutrition_plans").insert(data).execute()
    )


def get_plan_history(client_id: str) -> List[Dict[str, Any]]:
    """Получить все версии планов питания клиента."""
    supabase = _service_client()
    response = (
        supabase.table("nutrition_plans")
        .select("*")
        .eq("client_id", client_id)
        .order("version", desc=True)
        .execute()
    )
    return _extract_data(response) or []


def create_task(
    client_id: str,
    title: str,
    created_by: str,
    description: Optional[str] = None,
    due_date: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Создать задачу клиенту."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "title": title,
        "description": description,
        "created_by": created_by,
        "due_date": due_date,
        "plan_id": plan_id,
        "status": "pending",
    }
    return _extract_data(
        supabase.table("tasks").insert(data).execute()
    )


def complete_task(task_id: str, confirmation_payload: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Отметить задачу как выполненную."""
    supabase = _service_client()
    from datetime import datetime

    updates = {
        "status": "completed",
        "completed_at": datetime.utcnow().isoformat(),
    }

    # Если есть подтверждение (фото, текст), записываем в client_events
    if confirmation_payload:
        task = _execute_single(
            supabase.table("tasks").select("client_id").eq("id", task_id).single()
        )
        if task:
            log_client_event(
                client_id=task["client_id"],
                event_type="task_completed",
                severity="low",
                payload={"task_id": task_id, **confirmation_payload},
            )

    return _execute_one(
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
    )


def get_pending_tasks(client_id: str) -> List[Dict[str, Any]]:
    """Получить активные задачи клиента."""
    supabase = _service_client()
    response = (
        supabase.table("tasks")
        .select("*")
        .eq("client_id", client_id)
        .eq("status", "pending")
        .order("due_date", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def get_overdue_tasks(client_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получить просроченные задачи (все или по клиенту)."""
    supabase = _service_client()
    from datetime import datetime

    query = (
        supabase.table("tasks")
        .select("*")
        .eq("status", "pending")
        .lt("due_date", datetime.utcnow().isoformat())
    )

    if client_id:
        query = query.eq("client_id", client_id)

    response = query.execute()
    return _extract_data(response) or []


def mark_tasks_overdue(task_ids: List[str]) -> int:
    """
    Перевести задачи в статус 'overdue' (P2-6). Возвращает число обновлённых.

    До этого статус 'overdue' существовал в CHECK-констрейнте, но не проставлялся никогда:
    get_overdue_tasks() вычислял просрочку на лету и никем не вызывался, поэтому и клиент,
    и нутрициолог видели просроченные задачи как обычные 'pending'.
    """
    if not task_ids:
        return 0
    supabase = _service_client()
    rows = _extract_data(
        supabase.table("tasks").update({"status": "overdue"}).in_("id", task_ids).execute()
    )
    return len(rows or [])


# =============================================
# НАПОМИНАНИЯ (Фаза 1) — см. docs/spec_reminders.md
# =============================================


def create_reminder(
    client_id: str,
    title: str,
    remind_at: str,
    recurrence: str = "daily",
    weekday: Optional[int] = None,
    remind_date: Optional[str] = None,
    requires_response: bool = False,
    expected_response: Optional[str] = None,
    followup_after_hours: Optional[int] = None,
    max_followups: Optional[int] = None,
    response_deadline: Optional[str] = None,
    created_by: str = "nutritionist",
) -> Optional[Dict[str, Any]]:
    """Создать напоминание клиенту."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "title": title,
        "remind_at": remind_at,
        "recurrence": recurrence,
        "weekday": weekday,
        "remind_date": remind_date,
        "requires_response": requires_response,
        "expected_response": expected_response,
        "followup_after_hours": followup_after_hours,
        "max_followups": max_followups,
        "response_deadline": response_deadline,
        "created_by": created_by,
    }
    return _execute_one(supabase.table("reminders").insert(data))


def update_reminder(reminder_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Обновить поля напоминания (partial)."""
    supabase = _service_client()
    from datetime import datetime

    payload = {k: v for k, v in updates.items() if v is not None}
    payload["updated_at"] = datetime.utcnow().isoformat()
    return _execute_one(
        supabase.table("reminders").update(payload).eq("id", reminder_id)
    )


def delete_reminder(reminder_id: str) -> None:
    """Удалить напоминание (срабатывания уйдут каскадом)."""
    supabase = _service_client()
    supabase.table("reminders").delete().eq("id", reminder_id).execute()


def get_reminders_by_client(client_id: str) -> List[Dict[str, Any]]:
    """Все напоминания клиента (для редактора нутрициолога)."""
    supabase = _service_client()
    response = (
        supabase.table("reminders")
        .select("*")
        .eq("client_id", client_id)
        .order("remind_at", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def get_active_reminders() -> List[Dict[str, Any]]:
    """Все активные напоминания + данные клиента (telegram_id, timezone) для планировщика."""
    supabase = _service_client()
    response = (
        supabase.table("reminders")
        .select("*, clients(telegram_id, timezone)")
        .eq("active", True)
        .execute()
    )
    return _extract_data(response) or []


def occurrence_exists(reminder_id: str, due_date: str) -> bool:
    """Было ли уже срабатывание этого напоминания в указанную локальную дату."""
    supabase = _service_client()
    response = (
        supabase.table("reminder_occurrences")
        .select("id")
        .eq("reminder_id", reminder_id)
        .eq("due_date", due_date)
        .limit(1)
        .execute()
    )
    return bool(_extract_data(response))


def record_occurrence(
    reminder_id: str,
    client_id: str,
    due_date: str,
    next_followup_at: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Зафиксировать срабатывание (дедуп гарантирован UNIQUE reminder_id+due_date).

    next_followup_at задаётся для ждущих ответа напоминаний (когда слать первый повтор).
    """
    supabase = _service_client()
    data: Dict[str, Any] = {
        "reminder_id": reminder_id, "client_id": client_id, "due_date": due_date,
        "last_notified_date": due_date,  # P1-7: точка отсчёта дедупа по теме на сегодня
    }
    if next_followup_at is not None:
        data["next_followup_at"] = next_followup_at
    return _execute_one(supabase.table("reminder_occurrences").insert(data))


def has_topic_message_today(
    client_id: str, topic: Optional[str], day: str, exclude_occurrence_id: Optional[str] = None
) -> bool:
    """
    Кросс-джобовый дедуп напоминаний по теме (P1-7): было ли клиенту сегодня УЖЕ отправлено
    сообщение по теме `topic` (reminders.expected_response) — неважно, через утренний пакет
    (record_occurrence) или повтор (bump_occurrence_followup), и неважно от какого именно
    reminder. Раньше повторы считались только per-occurrence — если у клиента больше одного
    активного напоминания с одной темой (напр. два про воду), каждое слало независимо.

    Без темы (None/'text'/'none') дедуп не применяется — это не измеримый показатель,
    несколько разных текстовых напоминаний в день не считаются «одним и тем же вопросом».

    `exclude_occurrence_id` — исключить конкретное срабатывание из проверки (используется
    при рассмотрении его же собственного повтора: его last_notified_date уже сегодня по
    определению, иначе он бы всегда блокировал сам себя).
    """
    if not topic or topic in ("text", "none"):
        return False
    supabase = _service_client()
    reminders_resp = (
        supabase.table("reminders").select("id")
        .eq("client_id", client_id).eq("expected_response", topic)
        .execute()
    )
    reminder_ids = [r["id"] for r in (_extract_data(reminders_resp) or []) if r.get("id")]
    if not reminder_ids:
        return False
    query = (
        supabase.table("reminder_occurrences").select("id")
        .in_("reminder_id", reminder_ids)
        .eq("last_notified_date", day)
    )
    if exclude_occurrence_id:
        query = query.neq("id", exclude_occurrence_id)
    occ_resp = query.limit(1).execute()
    return bool(_extract_data(occ_resp))


# ── Контроль ответа (Слайс 2B) ────────────────────────────────────────────────


def get_open_occurrences() -> List[Dict[str, Any]]:
    """
    Открытые срабатывания (status='sent') с данными напоминания и клиента — для пассов
    детекта/догона/«сдались». Фильтр requires_response/active делается вызывающим (Python).
    """
    supabase = _service_client()
    response = (
        supabase.table("reminder_occurrences")
        .select("*, reminders(title, expected_response, requires_response, active, "
                "followup_after_hours, max_followups, response_deadline), "
                "clients(telegram_id, timezone)")
        .eq("status", "sent")
        .execute()
    )
    return _extract_data(response) or []


# Приёмы пищи привязаны к моменту дня: пропуск к дедлайну → алерт нутрициологу, и на этом всё.
# Тащить их «со вчера» в следующее сообщение бессмысленно (момент прошёл), поэтому исключаем.
_MEAL_EXPECTED = ("breakfast", "lunch", "dinner")


def get_outstanding_occurrences(client_id: str, due_date: str) -> List[Dict[str, Any]]:
    """
    Незакрытые (без ответа) срабатывания ждущих ответа напоминаний за указанную локальную
    дату — для вплетения в следующее сообщение («вчера не прислали воду»). Приёмы пищи
    исключаются: они one-shot в пределах дня (пропуск → алерт), на завтра не переносятся.
    """
    supabase = _service_client()
    response = (
        supabase.table("reminder_occurrences")
        .select("*, reminders(title, expected_response, requires_response, active)")
        .eq("client_id", client_id)
        .eq("due_date", due_date)
        .neq("status", "answered")
        .execute()
    )
    rows = _extract_data(response) or []
    return [
        r for r in rows
        if (r.get("reminders") or {}).get("requires_response")
        and (r.get("reminders") or {}).get("active")
        and (r.get("reminders") or {}).get("expected_response") not in _MEAL_EXPECTED
    ]


def mark_occurrence_answered(
    occurrence_id: str, response_ref: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Закрыть срабатывание как отвеченное (ответ получен)."""
    from datetime import datetime

    supabase = _service_client()
    payload = {"status": "answered", "resolved_at": datetime.utcnow().isoformat()}
    if response_ref is not None:
        payload["response_ref"] = response_ref
    return _execute_one(
        supabase.table("reminder_occurrences").update(payload).eq("id", occurrence_id)
    )


def mark_occurrence_expired(occurrence_id: str) -> Optional[Dict[str, Any]]:
    """Закрыть срабатывание как просроченное (ответа так и не пришло)."""
    from datetime import datetime

    supabase = _service_client()
    return _execute_one(
        supabase.table("reminder_occurrences")
        .update({"status": "expired", "resolved_at": datetime.utcnow().isoformat()})
        .eq("id", occurrence_id)
    )


def bump_occurrence_followup(
    occurrence_id: str, next_followup_at: Optional[str], notified_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Инкремент счётчика повторов + новое время следующего повтора. `notified_date` (P1-7) —
    локальная дата клиента, когда повтор реально ушёл; обновляет last_notified_date, чтобы
    другие напоминания с той же темой (expected_response) не спрашивали о том же сегодня же.
    """
    supabase = _service_client()
    row = _execute_single(
        supabase.table("reminder_occurrences").select("followups_sent").eq("id", occurrence_id).single()
    )
    sent = (row or {}).get("followups_sent") or 0
    payload: Dict[str, Any] = {"followups_sent": sent + 1, "next_followup_at": next_followup_at}
    if notified_date is not None:
        payload["last_notified_date"] = notified_date
    return _execute_one(
        supabase.table("reminder_occurrences").update(payload).eq("id", occurrence_id)
    )


def _count_since(query, since: str) -> int:
    """Есть ли хотя бы одна строка после `since` (created_at)."""
    rows = _extract_data(query.gt("created_at", since).limit(1).execute())
    return len(rows or [])


def has_measurement_since(client_id: str, column: str, since: str) -> bool:
    """Появился ли замер по колонке measurements (weight/waist/neck/hips) после `since`."""
    supabase = _service_client()
    q = (
        supabase.table("measurements").select("id")
        .eq("client_id", client_id).not_.is_(column, "null")
    )
    return _count_since(q, since) > 0


def has_client_metric_since(client_id: str, metric_key: str, since: str) -> bool:
    """Появилось ли значение показателя client_metrics (sleep/custom) после `since`."""
    supabase = _service_client()
    q = (
        supabase.table("client_metrics").select("id")
        .eq("client_id", client_id).eq("metric_key", metric_key)
    )
    return _count_since(q, since) > 0


def has_lab_result_since(client_id: str, since: str) -> bool:
    """Появились ли анализы после `since`."""
    supabase = _service_client()
    q = supabase.table("lab_results").select("id").eq("client_id", client_id)
    return _count_since(q, since) > 0


def has_client_message_since(client_id: str, since: str) -> bool:
    """Прислал ли клиент любое сообщение после `since` (для типа 'text')."""
    supabase = _service_client()
    q = (
        supabase.table("conversations").select("id")
        .eq("client_id", client_id).eq("role", "client")
    )
    return _count_since(q, since) > 0


def has_event_since(client_id: str, event_type: str, since: str) -> bool:
    """Было ли событие данного типа (напр. water_logged) после `since`."""
    supabase = _service_client()
    q = (
        supabase.table("client_events").select("id")
        .eq("client_id", client_id).eq("event_type", event_type)
    )
    # client_events помечаются event_date, а не created_at.
    rows = _extract_data(q.gt("event_date", since).limit(1).execute())
    return len(rows or []) > 0


def has_meal_event_since(client_id: str, meal_type: str, since: str) -> bool:
    """Был ли приём пищи нужного типа (breakfast/lunch/dinner) после `since`."""
    supabase = _service_client()
    q = (
        supabase.table("client_events").select("id")
        .eq("client_id", client_id).eq("event_type", "calories_logged")
        .filter("payload_json->>meal_type", "eq", meal_type)
    )
    rows = _extract_data(q.gt("event_date", since).limit(1).execute())
    return len(rows or []) > 0


def create_wellness_plan(
    client_id: str,
    sleep_target: Optional[str] = None,
    activity_target: Optional[str] = None,
    recovery: Optional[str] = None,
    stress_management: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Создать план ЗОЖ."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "sleep_target": sleep_target,
        "activity_target": activity_target,
        "recovery": recovery,
        "stress_management": stress_management,
        "notes": notes,
    }
    return _extract_data(
        supabase.table("wellness_plans").insert(data).execute()
    )


def get_wellness_plan(client_id: str) -> Optional[Dict[str, Any]]:
    """Получить активный план ЗОЖ клиента."""
    supabase = _service_client()
    return _execute_single(
        supabase.table("wellness_plans")
        .select("*")
        .eq("client_id", client_id)
        .order("created_at", desc=True)
        .limit(1)
        .single()
    )


def update_wellness_plan(
    client_id: str,
    updates: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Обновить план ЗОЖ (последний созданный)."""
    supabase = _service_client()

    # Находим последний план
    plan = get_wellness_plan(client_id)
    if not plan:
        return None

    return _execute_one(
        supabase.table("wellness_plans")
        .update(updates)
        .eq("id", plan["id"])
    )


def get_all_clients(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получить список всех клиентов (для нутрициолога)."""
    supabase = _service_client()
    query = supabase.table("clients").select("*").order("created_at", desc=True)

    if status:
        query = query.eq("client_status", status)

    response = query.execute()
    return _extract_data(response) or []


def get_client_registry(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Реестр клиентов из client_registry_view (с агрегацией):
    статусы, цель, вес, версия активного плана, последняя активность, открытые задачи.
    Опциональный фильтр по client_status.
    """
    supabase = _service_client()
    query = supabase.table("client_registry_view").select("*")

    if status:
        query = query.eq("client_status", status)

    response = query.execute()
    return _extract_data(response) or []


def write_audit_log(
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Записать действие в audit_log."""
    supabase = _service_client()
    data = {
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "old_value": old_value,
        "new_value": new_value,
    }
    return _extract_data(
        supabase.table("audit_logs").insert(data).execute()
    )


def get_audit_logs(
    entity_type: Optional[str] = None,
    actor_type: Optional[str] = None,
    action: Optional[str] = None,
    before: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Журнал аудита для просмотра нутрициологом (P2-8): таблица пишется с самого начала
    (write_audit_log из множества мест), но пути чтения не было — записи были видны
    только прямым SQL-запросом к БД. Фильтры опциональны, свежие сверху; курсорная
    пагинация по timestamp через `before` (для кнопки «Загрузить ещё»).
    """
    supabase = _service_client()
    query = supabase.table("audit_logs").select("*")
    if entity_type:
        query = query.eq("entity_type", entity_type)
    if actor_type:
        query = query.eq("actor_type", actor_type)
    if action:
        query = query.eq("action", action)
    if before:
        query = query.lt("timestamp", before)
    response = query.order("timestamp", desc=True).limit(limit).execute()
    return _extract_data(response) or []


def get_clients_by_ids(client_ids: List[str]) -> List[Dict[str, Any]]:
    """Имена клиентов по списку id — для подстановки читаемых имён в журнал аудита."""
    if not client_ids:
        return []
    supabase = _service_client()
    response = (
        supabase.table("clients").select("id, name").in_("id", client_ids).execute()
    )
    return _extract_data(response) or []


# =============================================
# ФУНКЦИИ ДЛЯ N8N (АВТОМАТИЗАЦИЯ)
# =============================================


def get_clients_for_weekly_report() -> List[Dict[str, Any]]:
    """
    Получить список active клиентов для еженедельного отчёта нутрициологу.
    Планировщик: run_weekly_report (api/scheduler.py), Пн 09:00 в TZ владельца.
    """
    supabase = _service_client()
    response = (
        supabase.table("clients")
        .select("id, name, client_status, payment_status")
        .eq("client_status", "active")
        .order("name", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def get_clients_for_audit(statuses: List[str]) -> List[Dict[str, Any]]:
    """
    Клиенты, подходящие под проактивный аудит (NEW-1) — по списку допустимых
    client_status. Список задаёт вызывающий (api/scheduler.py::AUDIT_ELIGIBLE_STATUSES),
    здесь — просто выборка, чтобы критерии аудита не были завязаны на список клиентов
    еженедельного отчёта (get_clients_for_weekly_report) — они меняются независимо.
    """
    if not statuses:
        return []
    supabase = _service_client()
    response = (
        supabase.table("clients")
        .select("id, name, client_status, nutritionist_notes")
        .in_("client_status", statuses)
        .order("name", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def insert_audit_finding(
    client_id: str, title: str, description: str, severity: str = "medium",
) -> Optional[Dict[str, Any]]:
    """Записать находку проактивного аудита клиента (NEW-1) — только когда что-то найдено."""
    supabase = _service_client()
    return _execute_one(
        supabase.table("client_audit_findings").insert({
            "client_id": client_id,
            "title": title,
            "description": description,
            "severity": severity,
        })
    )


def get_audit_findings(client_id: str, status: str = "open") -> List[Dict[str, Any]]:
    """Находки аудита клиента (по умолчанию только открытые), свежие сверху."""
    supabase = _service_client()
    query = supabase.table("client_audit_findings").select("*").eq("client_id", client_id)
    if status:
        query = query.eq("status", status)
    response = query.order("created_at", desc=True).execute()
    return _extract_data(response) or []


def dismiss_audit_finding(finding_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Отметить находку аудита как рассмотренную (не удаляем — история сохраняется)."""
    from datetime import datetime

    supabase = _service_client()
    return _execute_one(
        supabase.table("client_audit_findings")
        .update({
            "status": "dismissed",
            "dismissed_at": datetime.utcnow().isoformat(),
            "dismissed_by": user_id,
        })
        .eq("id", finding_id)
    )


def get_clients_with_inactive_payment() -> List[Dict[str, Any]]:
    """
    Получить клиентов с неактивной оплатой для напоминания нутрициологу.
    Планировщика для этого сейчас нет — функция доступна агенту/кабинету по запросу.
    """
    supabase = _service_client()
    response = (
        supabase.table("clients")
        .select("id, name, telegram_id, payment_status, client_status")
        .eq("payment_status", "inactive")
        .in_("client_status", ["active", "paused"])
        .order("name", desc=False)
        .execute()
    )
    return _extract_data(response) or []


def get_critical_alerts(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Получить критичные алерты за последние N часов.
    Планировщик: run_nutritionist_alerts (api/scheduler.py) шлёт свежие алерты в Telegram.
    """
    supabase = _service_client()
    from datetime import datetime, timedelta

    time_threshold = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

    response = (
        supabase.table("client_events")
        .select("*, clients!inner(id, name, telegram_id)")
        .eq("severity", "critical")
        .gte("event_date", time_threshold)
        .order("event_date", desc=True)
        .execute()
    )
    return _extract_data(response) or []


def trigger_alert_webhook(
    client_id: str,
    severity: str,
    alert_type: str,
    message: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Записать алерт и вернуть данные для отправки нутрициологу.
    business_rules вызывают эту функцию при критичных событиях.
    """
    # Записываем событие
    event = log_client_event(
        client_id=client_id,
        event_type=alert_type,
        severity=severity,
        payload=payload or {},
    )

    # Получаем данные клиента
    client = get_client_by_id(client_id)

    if event and client:
        return {
            "event": event,
            "client": client,
            "message": message,
            "severity": severity,
            "alert_type": alert_type,
        }

    return None


def get_client_summary(client_id: str, days: int = 7) -> Dict[str, Any]:
    """
    Получить сводку по клиенту за последние N дней (для еженедельного отчёта).
    """
    from datetime import datetime, timedelta

    time_threshold = (datetime.utcnow() - timedelta(days=days)).isoformat()

    # Клиент
    client = get_client_by_id(client_id)
    if not client:
        return {}

    # События за период
    supabase = _service_client()
    events_response = (
        supabase.table("client_events")
        .select("*")
        .eq("client_id", client_id)
        .gte("event_date", time_threshold)
        .execute()
    )
    events = _extract_data(events_response) or []

    # Количество сообщений
    conversations_response = (
        supabase.table("conversations")
        .select("id", count="exact")
        .eq("client_id", client_id)
        .gte("message_timestamp", time_threshold)
        .execute()
    )
    message_count = conversations_response.count if hasattr(conversations_response, 'count') else 0

    # Задачи
    tasks = get_tasks_by_client(client_id)
    pending_tasks = [t for t in tasks if t.get("status") == "pending"]
    completed_tasks = [t for t in tasks if t.get("status") == "completed"]

    # Алерты по severity
    critical_events = [e for e in events if e.get("severity") == "critical"]
    high_events = [e for e in events if e.get("severity") == "high"]

    return {
        "client": client,
        "period_days": days,
        "message_count": message_count,
        "total_events": len(events),
        "critical_alerts": len(critical_events),
        "high_alerts": len(high_events),
        "pending_tasks": len(pending_tasks),
        "completed_tasks": len(completed_tasks),
        "recent_events": events[:5],  # Последние 5 событий
    }
