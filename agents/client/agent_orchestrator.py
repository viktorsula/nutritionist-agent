"""
LLM-оркестратор ветки клиента (Фаза 1, за фиче-флагом).

Вместо жёсткого графа рёбер (determine→load_context→dispatch→…) — ОДИН узел-агент на
модели с надёжным tool-calling (Claude). Модель сама понимает тему хода, сама решает,
какими инструментами воспользоваться и какой контекст подгрузить, и сама формулирует ответ.

Инструменты — тонкие обёртки над УЖЕ существующими функциями (ничего не дублируем):
- log_meal/water/weight/wellbeing/labs → intake_store.persist_record (запись + medical-алерты);
- get_client_data → чтение данных клиента по требованию (реализует «сколько контекста грузить»);
- search_knowledge → pgvector-поиск для советов.

Безопасность (алерты/маршрутизация нутрициологу) остаётся ДЕТЕРМИНИРОВАННОЙ — её считает
persist_record через business_rules, не сама модель.

Границы Фазы 1: обрабатываем ТЕКСТ и ГОЛОС (голос → текст через Whisper). ФОТО пока уходит
на старый граф (call_llm ещё текст-в-текст; мультимодальность — следующий шаг). При любой
ошибке/недоступности LLM — откат на граф (ловит вызывающий process_client_message).

Параллелизм по id: per-client_id блокировка — быстрые сообщения одного клиента
сериализуются, разные клиенты идут независимо. Полный async — Фаза 3.
"""

import os
import base64
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from prompts import load_prompt
from agents.core.agent_engine import run_agent
from .state import create_initial_state, extract_response
from .intake_present import format_list, format_allergies
from . import intake_store

logger = logging.getLogger(__name__)

# Ф1.5: фото обрабатывается оркестратором (мультимодальность). Стратегия расшифровки
# (Claude видит фото vs Gemini-инструмент) выбирается per-kind через resolve_vision_strategy.
_SUPPORTED_TYPES = ("text", "voice", "photo")


# ==========================================
# ФИЧЕ-ФЛАГ
# ==========================================

def should_use(client_id: str, message_type: str = "text") -> bool:
    """
    Включён ли LLM-оркестратор для этого клиента и типа сообщения.

    ENV:
    - CLIENT_ORCHESTRATOR_ENABLED — глобальный тумблер (1/true/yes/on).
    - CLIENT_ORCHESTRATOR_CLIENT_IDS — белый список id через запятую (пусто = все, кто включён).

    Ф1.5: текст, голос И фото идут через оркестратор (мультимодальность). Прочие типы
    (документ и т.п.) — на граф.
    """
    if os.environ.get("CLIENT_ORCHESTRATOR_ENABLED", "").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    if message_type not in _SUPPORTED_TYPES:
        return False
    allow = os.environ.get("CLIENT_ORCHESTRATOR_CLIENT_IDS", "").strip()
    if allow:
        allowed = {x.strip() for x in allow.split(",") if x.strip()}
        return client_id in allowed
    return True


# ==========================================
# ПЕР-КЛИЕНТ БЛОКИРОВКА (изоляция параллельных диалогов)
# ==========================================

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(client_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _locks.get(client_id)
        if lock is None:
            lock = threading.Lock()
            _locks[client_id] = lock
        return lock


# ==========================================
# ГЛАВНЫЙ ВХОД
# ==========================================

def process(
    client_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any],
    access_info: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Полный проход оркестратора для одного хода. Возвращает тот же контракт, что и граф
    (extract_response). Может бросить LLMUnavailableError / прочие исключения — их ловит
    вызывающий и откатывается на граф.
    """
    from .orchestrator import ingest_node, save_to_db_node

    start = datetime.now()
    with _lock_for(client_id):
        state = create_initial_state(
            client_id=client_id,
            message=message,
            channel=channel,
            message_type=message_type,
            metadata=metadata,
            access_info=access_info,
        )

        # Нормализация вложений: голос → текст (Whisper); фото → image_kind (classify_image).
        ingest_node(state)
        _load_base_context(state)

        # Ф1.5: расшифровка фото. direct → image-блоки в Claude; gemini_tool → Gemini
        # расшифровывает и кладёт распознанное в контекст хода (оркестратор решает).
        images = _prepare_vision(state)

        reply = _run_agent_loop(state, images)
        state["agent_response"] = reply
        _finalize(state, reply)

        save_to_db_node(state)

        state["processing_time_ms"] = int((datetime.now() - start).total_seconds() * 1000)
        logger.info(
            f"Orchestrator handled client {client_id}: "
            f"tools={(state.get('metadata') or {}).get('tool_calls')}, "
            f"alerts={len(state.get('alerts') or [])}"
        )
        return extract_response(state)


# ==========================================
# КОНТЕКСТ (лёгкий базовый; остальное — инструментом по требованию)
# ==========================================

def _load_base_context(state: Dict[str, Any]) -> None:
    """Дешёвый контекст, нужный любому ходу: клиент/профиль/план/история/сводка/замер."""
    from database import queries

    client_id = state["client_id"]
    try:
        client = queries.get_client_by_id(client_id) or {}
        state["client"] = client

        profile = queries.get_client_profile(client_id) or {}
        if isinstance(profile, dict):
            profile = {**profile, "name": client.get("name")}
        state["client_profile"] = profile

        state["active_plan"] = queries.get_active_nutrition_plan(client_id)
        state["nutritionist_notes"] = client.get("nutritionist_notes")
        state["conversation_summary"] = client.get("conversation_summary") or ""

        history: List[Dict[str, str]] = []
        for conv in reversed(queries.get_conversations(client_id=client_id, limit=10)):
            text = conv.get("message_text") or conv.get("message") or ""
            if not text:
                continue
            role = "user" if conv.get("role") == "client" else "assistant"
            history.append({"role": role, "content": text})
        state["conversation_history"] = history

        try:
            state["latest_measurement"] = queries.get_latest_measurement(client_id)
        except Exception as e:
            logger.warning(f"orchestrator: latest_measurement failed: {e}")
            state["latest_measurement"] = None

        try:
            state["controlled_metrics"] = queries.get_controlled_metrics(client_id) or []
        except Exception as e:
            logger.warning(f"orchestrator: controlled_metrics failed: {e}")
            state["controlled_metrics"] = []
    except Exception as e:
        logger.error(f"orchestrator: base context load failed: {e}", exc_info=True)


# ==========================================
# РАСШИФРОВКА ФОТО (шов A/B, граница — IntakeRecord)
# ==========================================

def _image_block(image_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Anthropic image-блок из сырых байтов (base64)."""
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type or "image/jpeg",
            "data": base64.standard_b64encode(image_bytes).decode("utf-8"),
        },
    }


def _prepare_vision(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Готовит расшифровку фото по стратегии (per-kind, из llm_config):

    - "direct" (A): возвращает image-блоки — Claude видит фото сам, вместе с подписью и
      назначениями (один reasoning-цикл, связный ответ).
    - "gemini_tool" (B): Gemini расшифровывает → распознанное кладём текстом в контекст хода,
      оркестратор решает (прежняя схема). image-блоки не возвращаем ([]).

    Инвариант обоих путей: фактическая запись идёт через log_*-инструменты → validate →
    persist_record (IntakeRecord — граница, а не механизм зрения).
    """
    if state.get("message_type") != "photo":
        return []
    metadata = state.get("metadata") or {}
    image_bytes = metadata.get("image_bytes")
    if not image_bytes:
        return []

    kind = state.get("image_kind") or "food"
    mime = metadata.get("mime_type", "image/jpeg")

    from utils.vision import resolve_vision_strategy

    strategy = resolve_vision_strategy(kind)
    logger.info(f"Vision strategy for client {state['client_id']} kind={kind}: {strategy}")

    if strategy == "direct":
        return [_image_block(image_bytes, mime)]

    _gemini_preextract(state, image_bytes, kind, mime)
    return []


def _gemini_preextract(state: Dict[str, Any], image_bytes: bytes, kind: str, mime: str) -> None:
    """
    Вариант B: Gemini-инструмент расшифровывает фото, распознанное подмешиваем текстом в
    сообщение хода — оркестратор (Claude) дальше сам решает, что записать/ответить. Ошибка
    зрения не валит ход: просто идём без распознанного (Claude попросит уточнить).
    """
    from utils import vision

    note: Optional[str] = None
    try:
        if kind == "lab_document":
            data = vision.analyze_lab_document(image_bytes, mime_type=mime) or {}
            labs = data.get("labs") or data.get("results") or []
            if labs:
                note = "На фото распознан бланк анализов: " + "; ".join(
                    f"{l.get('indicator')} {l.get('value')} {l.get('unit') or ''}".strip()
                    for l in labs if l.get("indicator") is not None
                )
        elif kind == "fridge":
            data = vision.analyze_fridge(image_bytes, mime_type=mime) or {}
            products = data.get("products") or data.get("items") or []
            if products:
                names = [p if isinstance(p, str) else p.get("name") for p in products]
                note = "На фото холодильника распознаны продукты: " + format_list(
                    [n for n in names if n]
                )
        else:  # food
            data = vision.analyze_food_plate(image_bytes, mime_type=mime) or {}
            items = data.get("items") or data.get("ingredients") or []
            names = [it if isinstance(it, str) else it.get("name") for it in items]
            names = [n for n in names if n]
            if names:
                note = "На фото распознана еда: " + format_list(names)
    except Exception as e:
        logger.warning(f"_gemini_preextract failed (kind={kind}): {e}")

    if note:
        base = (state.get("message") or "").strip()
        state["message"] = f"{base}\n\n[{note}]".strip() if base else f"[{note}]"


# ==========================================
# ЦИКЛ АГЕНТА
# ==========================================

def _run_agent_loop(state: Dict[str, Any], images: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Клиентский адаптер поверх общего движка: собирает промпт/инструменты/обработчики
    (всё scoped по client_id) и вызывает role-agnostic run_agent. task_type='orchestrator'
    → модель из llm_config (кабинет нутрициолога). images — image-блоки текущего хода
    (стратегия direct); при пустом списке ход текстовый.
    """
    result = run_agent(
        system_prompt=_system_prompt(state),
        history=state.get("conversation_history"),
        user_message=state.get("message"),
        tools=_tool_schemas(),
        tool_handlers=_build_handlers(state),
        task_type="orchestrator",
        images=images or None,
    )
    state["llm_model"] = result.model
    state["llm_usage"] = result.usage
    state["agent_used"] = "orchestrator"

    if result.tool_calls:
        md = state.get("metadata") or {}
        md["tool_calls"] = [t.get("name") for t in result.tool_calls]
        state["metadata"] = md

    return result.content or "Принял. Расскажи, пожалуйста, чуть подробнее — и я помогу."


def _system_prompt(state: Dict[str, Any]) -> str:
    profile = state.get("client_profile") or {}
    view = _plan_view(state.get("active_plan"))
    try:
        template = load_prompt("client/orchestrator_system")
        system = template.format(
            client_name=profile.get("name", "Клиент"),
            restrictions=format_list(view.get("restrictions")),
            allergies=format_allergies(profile),
        )
    except Exception as e:
        logger.error(f"orchestrator system prompt error: {e}")
        system = (
            "Ты — ИИ-ассистент нутрициолога. Веди тёплый диалог на русском от первого лица, "
            "используй инструменты для записи данных и ответов, не выдумывай факты."
        )

    # Назначения нутрициолога — ОБЯЗАТЕЛЬНАЯ опора любого ответа (норма воды, калории,
    # рекомендации и т.д. приходят отсюда). Кладём всегда, а не «инструментом по требованию».
    prescriptions = _format_prescriptions(state, view)
    if prescriptions:
        system += "\n\n" + prescriptions

    # Контролируемые показатели: даём модели ТОЧНЫЕ ключи, чтобы произвольные показатели
    # (пульс/стресс/…) логировались под ключом каталога → детерминированный детект ответа
    # на напоминания (иначе custom-ключ модель выбирает наугад).
    metrics_block = _format_controlled_metrics(state)
    if metrics_block:
        system += "\n\n" + metrics_block

    summary = (state.get("conversation_summary") or "").strip()
    if summary:
        system += "\n\n## Память о клиенте (сводка прошлых разговоров)\n" + summary
    return system


def _plan_view(plan: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Нормализованный вид активного плана: назначения нутрициолога лежат в `plan_json`
    (`description`/`target_calories`/`restrictions`), БАДы — в `supplements_json.items`.
    Читаем ИЗ plan_json (редактор нутрициолога пишет туда), с фолбэком на верхний уровень
    (совместимость со старыми записями/тестами). Возвращает плоский словарь для подачи.
    """
    plan = plan or {}
    pj = plan.get("plan_json") if isinstance(plan.get("plan_json"), dict) else {}

    def pick(key: str) -> Any:
        val = pj.get(key)
        return val if val is not None else plan.get(key)

    supplements = plan.get("supplements_json")
    items = supplements.get("items") if isinstance(supplements, dict) else supplements

    return {
        "title": plan.get("title"),
        "description": pick("description"),          # свободный текст рекомендаций (в т.ч. вода)
        "target_calories": pick("target_calories"),
        "restrictions": pick("restrictions"),
        "water_ml_target": pick("water_ml_target"),  # если появится структурное поле
        "supplements": items,
    }


def _format_prescriptions(state: Dict[str, Any], view: Dict[str, Any]) -> str:
    """Обязательный контекст: назначения плана + заметки нутрициолога (опора ответа)."""
    lines: List[str] = []
    if view.get("title"):
        lines.append(f"- План: {view['title']}")
    if view.get("target_calories"):
        lines.append(f"- Целевые калории: {view['target_calories']} ккал/день")
    if view.get("water_ml_target"):
        lines.append(f"- Норма воды: {view['water_ml_target']} мл/день")
    restrictions = view.get("restrictions")
    if restrictions:
        lines.append("- Ограничения: " + format_list(restrictions))
    if view.get("supplements"):
        lines.append("- БАДы/добавки: " + format_list(view["supplements"]))
    if view.get("description"):
        lines.append(f"- Рекомендации нутрициолога: {view['description']}")

    notes = (state.get("client") or {}).get("nutritionist_notes")
    if notes:
        lines.append(f"- Заметки нутрициолога (внутреннее): {notes}")

    if not lines:
        return (
            "## Назначения нутрициолога\n"
            "Активный план ещё не заполнен. Если клиент спрашивает про норму воды/калории/"
            "рекомендации — честно скажи, что их пока не назначил нутрициолог, не выдумывай."
        )
    return (
        "## Назначения нутрициолога (обязательная опора ответа; не выдумывай сверх этого)\n"
        + "\n".join(lines)
    )


def _format_controlled_metrics(state: Dict[str, Any]) -> str:
    """Каталог контролируемых показателей клиента → точные ключи для log_measurement/log_sleep."""
    metrics = state.get("controlled_metrics") or []
    lines: List[str] = []
    for m in metrics:
        if not isinstance(m, dict):
            continue
        key = str(m.get("key") or "").strip()
        if not key:
            continue
        label = m.get("label_ru") or key
        if key == "sleep":
            lines.append(f'- {label} (во сколько лёг/встал) → инструмент log_sleep')
        else:
            unit = f', ед.: {m["unit"]}' if m.get("unit") else ""
            lines.append(f'- {label} → log_measurement(metric_key="{key}"{unit})')
    if not lines:
        return ""
    return (
        "## Контролируемые показатели клиента (нутрициолог их отслеживает)\n"
        "Если клиент сообщает значение одного из них — ОБЯЗАТЕЛЬНО запиши указанным инструментом "
        "с ТОЧНЫМ ключом (metric_key) ниже. Это вносит данные в карту и закрывает напоминания.\n"
        + "\n".join(lines)
    )


# ==========================================
# ИНСТРУМЕНТЫ: схемы (Anthropic) + обработчики
# ==========================================

def _tool_schemas() -> List[Dict[str, Any]]:
    kbju = {
        "type": "object",
        "properties": {
            "kcal": {"type": "number"}, "protein_g": {"type": "number"},
            "fat_g": {"type": "number"}, "carb_g": {"type": "number"},
            "sugar_g": {"type": "number"}, "fiber_g": {"type": "number"},
        },
        "description": "ОБЯЗАТЕЛЬНО заполни: оценка итогового КБЖУ приёма (ккал + белки/жиры/углеводы"
                       " + сахар). Оценивай приблизительно по известным блюдам/порциям — это нужно"
                       " для суточных тоталов и графиков питания. Без total приём не попадёт в динамику.",
    }
    return [
        {
            "name": "log_meal",
            "description": "Записать приём пищи/еду, о которой сообщил клиент. ВСЕГДА оценивай и"
                           " передавай `total` (КБЖУ приёма) — приблизительно, это нормально.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "Распознанные продукты/ингредиенты.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "amount": {"type": "string", "description": "напр. '200 г', '1 стакан'"},
                            },
                            "required": ["name"],
                        },
                    },
                    "dish_name": {"type": "string"},
                    "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack", "all_day"]},
                    "total": kbju,
                },
                "required": ["items"],
            },
        },
        {
            "name": "log_water",
            "description": "Записать выпитую воду в миллилитрах (стакан ≈ 250 мл).",
            "input_schema": {"type": "object", "properties": {"water_ml": {"type": "number"}}, "required": ["water_ml"]},
        },
        {
            "name": "log_weight",
            "description": "Записать вес клиента в килограммах.",
            "input_schema": {"type": "object", "properties": {"weight_kg": {"type": "number"}}, "required": ["weight_kg"]},
        },
        {
            "name": "log_wellbeing",
            "description": "Записать самочувствие клиента. При 'bad' обязательно указать причину.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["good", "normal", "bad"]},
                    "reason": {"type": "string"},
                },
                "required": ["status"],
            },
        },
        {
            "name": "log_labs",
            "description": "Записать результаты анализов клиента.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "labs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "indicator": {"type": "string"},
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                            },
                            "required": ["indicator", "value"],
                        },
                    }
                },
                "required": ["labs"],
            },
        },
        {
            "name": "log_measurement",
            "description": "Записать контролируемый показатель клиента: замер тела "
                           "(metric_key: waist=талия, neck=шея, hips=бёдра, chest=грудь, weight=вес) или "
                           "произвольный показатель нутрициолога (пульс, стресс и т.п.). Значение — число.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric_key": {"type": "string", "description": "ключ показателя (waist/neck/hips/chest/weight/пульс…)"},
                    "value": {"type": "number"},
                    "unit": {"type": "string", "description": "напр. 'см', 'уд/мин'"},
                },
                "required": ["metric_key", "value"],
            },
        },
        {
            "name": "log_sleep",
            "description": "Записать сон клиента: во сколько лёг и во сколько встал ('HH:MM'). "
                           "Продолжительность считается автоматически.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "bedtime": {"type": "string", "description": "время отхода ко сну, 'HH:MM'"},
                    "wake": {"type": "string", "description": "время подъёма, 'HH:MM'"},
                },
                "required": ["bedtime", "wake"],
            },
        },
        {
            "name": "get_client_data",
            "description": "Получить данные клиента для ответа на вопрос о его показателях/плане/дневнике. "
                           "scope='diary' — недавние записи дневника (что ел, сколько воды, вес, самочувствие) "
                           "для ответов вида «что я вчера ел / сколько воды выпил».",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string",
                              "enum": ["measurements", "labs", "plan", "wellness", "tasks", "diary"]},
                },
                "required": ["scope"],
            },
        },
        {
            "name": "search_knowledge",
            "description": "Найти релевантные знания (база нутрициолога + документы клиента) для совета.",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    ]


def _build_handlers(state: Dict[str, Any]) -> Dict[str, Any]:
    """Обработчики инструментов замыкаются на state текущего хода."""
    from .intake_schema import validate

    # Источник факта = модальность хода (photo, если Claude логирует с фото; иначе text).
    source = "photo" if state.get("message_type") == "photo" else "text"

    def _persist(record: Dict[str, Any], not_captured: str) -> str:
        # Инвариант: любая запись (text/photo, direct/gemini_tool) проходит validate-гейт
        # перед persist — как в графовом IntakeRecord-протоколе. low/пусто → не пишем.
        # validate работает по сырой записи; нормализацию делает сам persist_record (один раз).
        check = validate(record)
        if check.get("needs_clarify"):
            reasons = check.get("uncertainties") or check.get("issues") or []
            detail = f" ({'; '.join(str(x) for x in reasons)})" if reasons else ""
            return f"не записал: нужно уточнить у клиента{detail}"
        subtype = intake_store.persist_record(state, record)
        return f"записано: {subtype}" if subtype else f"не записано: {not_captured}"

    def log_meal(inp: Dict[str, Any]) -> str:
        items = [
            {"name": it.get("name"), "amount": it.get("amount")}
            for it in (inp.get("items") or []) if it.get("name")
        ]
        record = {
            "kind": "meal", "source": source, "confidence": "high",
            "meal": {
                "dish_name": inp.get("dish_name"),
                "meal_type": inp.get("meal_type"),
                "items": items,
                "total": inp.get("total") or {},
            },
        }
        return _persist(record, "не понял, что именно из еды")

    def log_water(inp: Dict[str, Any]) -> str:
        return _persist({"kind": "water", "source": source, "water_ml": inp.get("water_ml")},
                        "не понял объём воды")

    def log_weight(inp: Dict[str, Any]) -> str:
        return _persist({"kind": "weight", "source": source, "weight_kg": inp.get("weight_kg")},
                        "не понял значение веса")

    def log_wellbeing(inp: Dict[str, Any]) -> str:
        status = inp.get("status")
        result = _persist(
            {"kind": "wellbeing", "source": source,
             "wellbeing": {"status": status, "reason": inp.get("reason")}},
            "не понял самочувствие",
        )
        # Плохое самочувствие всегда уходит нутрициологу: событие-алерт в панели «Алерты»
        # + Telegram-пуш планировщиком (bad_wellbeing включён в get_recent_alert_events).
        # Сообщаем это модели, чтобы она сказала клиенту «я УЖЕ уведомила», а не «будет в курсе».
        if status == "bad" and result.startswith("записано"):
            result += (" — жалоба зафиксирована как алерт, нутрициолог уже уведомлён "
                       "(панель «Алерты» + Telegram). Скажи клиенту, что уже сообщил(а) нутрициологу.")
        return result

    def log_labs(inp: Dict[str, Any]) -> str:
        labs = [
            {"indicator": l.get("indicator"), "value": l.get("value"), "unit": l.get("unit")}
            for l in (inp.get("labs") or []) if l.get("indicator") is not None
        ]
        return _persist({"kind": "lab", "source": source, "labs": labs}, "не понял показатели анализов")

    def log_measurement(inp: Dict[str, Any]) -> str:
        return _persist(
            {"kind": "measurement", "source": source,
             "measurement": {"metric_key": inp.get("metric_key"), "value": inp.get("value"),
                             "unit": inp.get("unit")}},
            "не понял показатель или значение",
        )

    def log_sleep(inp: Dict[str, Any]) -> str:
        return _persist(
            {"kind": "sleep", "source": source,
             "sleep": {"bedtime": inp.get("bedtime"), "wake": inp.get("wake")}},
            "не понял время сна",
        )

    def get_client_data(inp: Dict[str, Any]) -> Any:
        from database import queries
        cid = state["client_id"]
        scope = inp.get("scope")
        if scope == "measurements":
            return queries.get_latest_measurement(cid)
        if scope == "labs":
            return queries.get_recent_lab_results(cid, limit=20)
        if scope == "plan":
            return _plan_view(state.get("active_plan") or queries.get_active_nutrition_plan(cid))
        if scope == "wellness":
            return queries.get_wellness_plan(cid)
        if scope == "tasks":
            return queries.get_pending_tasks(cid)
        if scope == "diary":
            # Недавние записи дневника: приёмы пищи (calories_logged), вода (water_logged),
            # вес (weight_logged), самочувствие (bad_wellbeing). Модель сама отберёт нужное
            # по дате/типу и ответит «что ел вчера / сколько воды».
            return queries.get_client_events(cid, limit=40)
        return f"неизвестный scope: {scope}"

    def search_knowledge(inp: Dict[str, Any]) -> str:
        from utils.knowledge import (
            search_knowledge_base, search_client_documents, build_context_from_chunks,
        )
        query = inp.get("query") or ""
        chunks = search_knowledge_base(query, match_count=4) + search_client_documents(
            query, state["client_id"], match_count=4
        )
        return build_context_from_chunks(chunks) or "по базе знаний ничего релевантного не найдено"

    return {
        "log_meal": log_meal,
        "log_water": log_water,
        "log_weight": log_weight,
        "log_wellbeing": log_wellbeing,
        "log_labs": log_labs,
        "log_measurement": log_measurement,
        "log_sleep": log_sleep,
        "get_client_data": get_client_data,
        "search_knowledge": search_knowledge,
    }


# ==========================================
# ФИНАЛИЗАЦИЯ (безопасность + формат)
# ==========================================

def _finalize(state: Dict[str, Any], reply: str) -> None:
    """
    Финальный текст клиенту = ответ модели КАК ЕСТЬ.

    В отличие от графа, оркестратор САМ вплетает предупреждения/уведомления в тёплый ответ
    (через данные, которые возвращают инструменты: log_wellbeing сообщает «нутрициолог уведомлён»,
    план-ограничения — в системном промпте). Поэтому НЕ дописываем сюда сырой текст алертов
    (`format_client_message`) — он дублировал ответ и звучал чуждо (третье лицо «Клиент…», «вы»).
    Детерминированная безопасность (событие-алерт + severity + Telegram-пуш нутрициологу) не
    зависит от этого текста — она в persist_record/routing/scheduler, а не в сообщении клиенту.
    """
    state["final_message"] = reply
