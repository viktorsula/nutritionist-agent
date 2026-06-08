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
    NotificationSchedule,
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
        supabase.table("document_metadata").insert(payload).select("*").execute()
    )


def get_document_metadata(document_id: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("document_metadata").select("*").eq("id", document_id).single()
    )


def insert_knowledge_base_chunk(chunk: KnowledgeBaseChunk) -> Any:
    supabase = _service_client()
    payload = {
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
        "source": chunk.source,
    }
    return _extract_data(
        supabase.table("knowledge_base").insert(payload).select("*").execute()
    )


def insert_client_document_chunk(chunk: ClientDocumentChunk) -> Any:
    supabase = _service_client()
    payload = {
        "client_id": str(chunk.client_id),
        "document_id": str(chunk.document_id),
        "chunk_index": chunk.chunk_index,
        "chunk_text": chunk.chunk_text,
        "embedding": chunk.embedding,
    }
    return _extract_data(
        supabase.table("client_documents").insert(payload).select("*").execute()
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


def get_system_setting(key: str) -> Optional[Dict[str, Any]]:
    supabase = _service_client()
    return _execute_single(
        supabase.table("system_settings").select("*").eq("key", key).single()
    )


def get_all_system_settings() -> List[Dict[str, Any]]:
    supabase = _service_client()
    response = supabase.table("system_settings").select("*").execute()
    return _extract_data(response) or []


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


# =============================================
# ФУНКЦИИ ДЛЯ BUSINESS_RULES
# =============================================


def get_client_profile(client_id: str) -> Optional[Dict[str, Any]]:
    """Получить медицинский профиль клиента (аллергии, пороги алертов)."""
    supabase = _service_client()
    return _execute_single(
        supabase.table("client_profiles").select("*").eq("client_id", client_id).single()
    )


def update_client(client_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Обновить профиль клиента (payment_status, access_status, client_status и др.)."""
    supabase = _service_client()
    return _execute_single(
        supabase.table("clients")
        .update(updates)
        .eq("id", client_id)
        .select("*")
        .single()
    )


def update_client_status(
    client_id: str,
    client_status: Optional[str] = None,
    payment_status: Optional[str] = None,
    access_status: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Обновить статусы клиента."""
    updates = {}
    if client_status is not None:
        updates["client_status"] = client_status
    if payment_status is not None:
        updates["payment_status"] = payment_status
    if access_status is not None:
        updates["access_status"] = access_status

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
        supabase.table("client_events").insert(data).select("*").execute()
    )


def get_client_events(
    client_id: str,
    severity: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Получить события клиента, опционально фильтр по severity."""
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

    response = query.execute()
    return _extract_data(response) or []


def get_notification_schedule(client_id: str) -> List[Dict[str, Any]]:
    """Получить расписание уведомлений клиента."""
    supabase = _service_client()
    response = (
        supabase.table("notification_schedule")
        .select("*")
        .eq("client_id", client_id)
        .execute()
    )
    return _extract_data(response) or []


def update_notification_schedule(
    client_id: str,
    notification_type: str,
    is_active: Optional[bool] = None,
    scheduled_time: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Обновить расписание уведомлений (вкл/откл, изменить время)."""
    supabase = _service_client()

    updates = {}
    if is_active is not None:
        updates["is_active"] = is_active
    if scheduled_time is not None:
        updates["scheduled_time"] = scheduled_time

    if not updates:
        return None

    return _execute_single(
        supabase.table("notification_schedule")
        .update(updates)
        .eq("client_id", client_id)
        .eq("notification_type", notification_type)
        .select("*")
        .single()
    )


def update_system_setting(key: str, value: Any, updated_by: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Обновить системную настройку."""
    supabase = _service_client()

    updates = {
        "value": value,
    }
    if updated_by:
        updates["updated_by"] = updated_by

    return _execute_single(
        supabase.table("system_settings")
        .update(updates)
        .eq("key", key)
        .select("*")
        .single()
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
        supabase.table("conversations").insert(data).select("*").execute()
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
        supabase.table("nutrition_plans").insert(data).select("*").execute()
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
        supabase.table("tasks").insert(data).select("*").execute()
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

    return _execute_single(
        supabase.table("tasks")
        .update(updates)
        .eq("id", task_id)
        .select("*")
        .single()
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
        supabase.table("wellness_plans").insert(data).select("*").execute()
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

    return _execute_single(
        supabase.table("wellness_plans")
        .update(updates)
        .eq("id", plan["id"])
        .select("*")
        .single()
    )


def get_all_clients(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Получить список всех клиентов (для нутрициолога)."""
    supabase = _service_client()
    query = supabase.table("clients").select("*").order("created_at", desc=True)

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
        supabase.table("audit_logs").insert(data).select("*").execute()
    )


# =============================================
# ФУНКЦИИ ДЛЯ N8N (АВТОМАТИЗАЦИЯ)
# =============================================


def get_notifications_due_now(notification_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Получить клиентов, которым пора отправить уведомление (с учётом timezone).
    n8n вызывает каждые 5 минут.

    Логика:
    1. Берём текущее время UTC
    2. Для каждого клиента конвертируем в его timezone
    3. Проверяем совпадение с scheduled_time
    4. Фильтруем: is_active=true, access_status=active, payment_status=active
    """
    supabase = _service_client()

    # Получаем все активные расписания с информацией о клиенте
    query = (
        supabase.table("notification_schedule")
        .select("*, clients!inner(id, name, telegram_id, timezone, access_status, payment_status)")
        .eq("is_active", True)
        .eq("clients.access_status", "active")
        .in_("clients.payment_status", ["trial", "active"])
    )

    if notification_type:
        query = query.eq("notification_type", notification_type)

    response = query.execute()
    schedules = _extract_data(response) or []

    # Фильтрация по времени происходит в n8n с помощью timezone conversion
    # Здесь возвращаем все активные расписания
    return schedules


def create_notification_schedule(
    client_id: str,
    notification_type: str,
    scheduled_time: str,
    timezone: str = "Asia/Dubai",
    is_active: bool = True,
) -> Optional[Dict[str, Any]]:
    """Создать расписание уведомлений для клиента."""
    supabase = _service_client()
    data = {
        "client_id": client_id,
        "notification_type": notification_type,
        "scheduled_time": scheduled_time,
        "timezone": timezone,
        "is_active": is_active,
    }
    return _extract_data(
        supabase.table("notification_schedule").insert(data).select("*").execute()
    )


def get_clients_for_weekly_report() -> List[Dict[str, Any]]:
    """
    Получить список active клиентов для еженедельного отчёта нутрициологу.
    n8n: каждый понедельник в 09:00.
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


def get_clients_with_inactive_payment() -> List[Dict[str, Any]]:
    """
    Получить клиентов с неактивной оплатой для напоминания нутрициологу.
    n8n: ежедневно в 10:00.
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
    n8n: проверка каждый час или по webhook от business_rules.
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
    Записать алерт и вернуть данные для отправки в n8n webhook.
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
