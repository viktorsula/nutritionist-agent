"""
Client Orchestrator — LangGraph граф для обработки сообщений клиента

Граф (линейный; тему выбирает единый определитель, а не модальность):
START
  ↓
ingest          (голос → текст через Whisper; фото → image_kind через classify_image)
  ↓
determine       (intake.determine_turn → segments[] + needs_answer)
  ↓
load_context    (контекст ПО ВЕТКАМ сегментов: intake — лёгкий+алерты; profile/advice — полнее)
  ↓
dispatch        (цикл по сегментам → обработчики:
                   intake  → vision/diary/document (persist + safety; текст = ack)
                   profile → dialog_agent          (ответ, знает клиента)
                   advice  → nutrition_agent        (RAG))
  ↓
format_response (склейка: предупреждения → ответы → квитанция)
  ↓
save_to_db      (conversations; события пишут сами обработчики)
  ↓
END
"""

import logging
from typing import Dict, Any, List, Callable
from datetime import datetime

from langgraph.graph import StateGraph, END

from prompts import load_prompt

from .state import ClientState, create_initial_state, extract_response
from .dialog_agent import dialog_node
from .vision_agent import vision_node
from .diary_agent import diary_node
from .nutrition_agent import nutrition_node
from .document_agent import document_node
from . import intake
from .branches import (
    ACK,
    ANSWER,
    CLARIFY,
    INTAKE,
    PROFILE,
    ADVICE,
    FALLBACK_BRANCH,
    label_ru,
    intake_subtype_meta,
)
from utils.llm import call_llm

logger = logging.getLogger(__name__)


# ==========================================
# ГЛАВНАЯ ФУНКЦИЯ (вызывается из router.py)
# ==========================================

def process_client_message(
    client_id: str,
    message: str,
    channel: str,
    message_type: str,
    metadata: Dict[str, Any],
    access_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Обрабатывает сообщение от клиента через LangGraph.

    Args:
        client_id: UUID клиента
        message: Текст сообщения
        channel: Канал ('telegram', 'web')
        message_type: Тип ('text', 'photo', 'voice')
        metadata: Дополнительные данные
        access_info: Результат check_access()

    Returns:
        {
            "message": str,
            "agent_used": str,
            "model": str,
            "processing_time_ms": int
        }
    """
    start_time = datetime.now()

    try:
        # Создание графа
        graph = create_client_graph()

        # Создание начального состояния
        initial_state = create_initial_state(
            client_id=client_id,
            message=message,
            channel=channel,
            message_type=message_type,
            metadata=metadata,
            access_info=access_info
        )

        # Выполнение графа
        final_state = graph.invoke(initial_state)

        # Вычисление времени обработки
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        final_state['processing_time_ms'] = int(processing_time)

        # Извлечение ответа
        return extract_response(final_state)

    except Exception as e:
        logger.error(f"Orchestrator error for client {client_id}: {e}", exc_info=True)
        return {
            "message": "Произошла ошибка при обработке сообщения. Попробуйте ещё раз.",
            "error": str(e),
            "agent_used": "error_handler"
        }


# ==========================================
# СОЗДАНИЕ LANGGRAPH ГРАФА
# ==========================================

def create_client_graph():
    """
    Создаёт LangGraph граф клиента (линейный; тему выбирает определитель).

    ingest → determine → load_context → dispatch → format_response → save_to_db → END
    Диспетчеризация по сегментам происходит ВНУТРИ узла dispatch (обработчики
    вызываются как функции), т.к. условие графа не разветвляется на несколько веток.
    """
    workflow = StateGraph(ClientState)

    workflow.add_node("ingest", ingest_node)
    workflow.add_node("determine", determine_node)
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("dispatch", dispatch_node)
    workflow.add_node("format_response", format_response_node)
    workflow.add_node("save_to_db", save_to_db_node)

    workflow.set_entry_point("ingest")
    workflow.add_edge("ingest", "determine")
    workflow.add_edge("determine", "load_context")
    workflow.add_edge("load_context", "dispatch")
    workflow.add_edge("dispatch", "format_response")
    workflow.add_edge("format_response", "save_to_db")
    workflow.add_edge("save_to_db", END)

    return workflow.compile()


# ==========================================
# УЗЛЫ ГРАФА
# ==========================================

def load_context_node(state: ClientState) -> ClientState:
    """
    Узел загрузки контекста ПО ВЕТКАМ сегментов (не «всё всегда»).

    Базовое (всегда, дёшево): клиент (имя/заметки) + медпрофиль (аллергии/цели) +
    активный план (restrictions/water_target) — нужны для безопасности и любой ветки.

    Расширенное (по присутствующим ветками):
    - intake  → последний замер (для алерта weight_increase); БЕЗ истории/labs/ЗОЖ/задач.
    - profile → история(10) + сводка + задачи + ЗОЖ + анализы + последний замер (диалог «знает клиента»).
    - advice  → сводка (для связности RAG-ответа); план/цели уже в базовом.
    """
    from database import queries

    client_id = state['client_id']

    branches = {s.get('branch') for s in (state.get('segments') or [])}
    if not branches:
        branches = {FALLBACK_BRANCH}
    has_intake = INTAKE in branches
    has_profile = PROFILE in branches
    has_advice = ADVICE in branches
    # profile грузит «диалоговый» контекст (история/сводка/задачи/анализы)
    conversational = has_profile or has_advice

    try:
        # ── Базовое (всегда) ───────────────────────────────────────────────
        client = queries.get_client_by_id(client_id) or {}
        state['client'] = client

        profile = queries.get_client_profile(client_id) or {}
        if isinstance(profile, dict):
            profile = {**profile, 'name': client.get('name')}
        state['client_profile'] = profile

        state['active_plan'] = queries.get_active_nutrition_plan(client_id)
        state['nutritionist_notes'] = client.get('nutritionist_notes')

        # ── Последний замер: intake (алерт по весу) или profile (озвучить вес) ─
        if has_intake or has_profile:
            try:
                state['latest_measurement'] = queries.get_latest_measurement(client_id)
            except Exception as e:
                logger.warning(f"Не удалось загрузить последний замер: {e}")
                state['latest_measurement'] = None
        else:
            state['latest_measurement'] = None

        # ── Анализы: озвучивает только диалоговая ветка (profile) ───────────
        if has_profile:
            try:
                state['lab_results'] = queries.get_recent_lab_results(client_id, limit=20)
            except Exception as e:
                logger.warning(f"Не удалось загрузить анализы: {e}")
                state['lab_results'] = []
        else:
            state['lab_results'] = []

        # ── ЗОЖ и задачи: только profile ───────────────────────────────────
        if has_profile:
            try:
                state['wellness_plan'] = queries.get_wellness_plan(client_id)
            except Exception as e:
                logger.warning(f"Не удалось загрузить план ЗОЖ: {e}")
                state['wellness_plan'] = None
            state['tasks'] = queries.get_pending_tasks(client_id)
        else:
            state['wellness_plan'] = None
            state['tasks'] = []

        # ── Долговременная/краткосрочная память диалога: profile/advice ─────
        if conversational:
            state['conversation_summary'] = client.get('conversation_summary') or ''
            conversations = queries.get_conversations(client_id=client_id, limit=10)
            history = []
            for conv in reversed(conversations):  # get_conversations отдаёт по убыванию
                db_role = conv.get('role')
                text = conv.get('message_text') or conv.get('message') or ''
                if not text:
                    continue
                llm_role = 'user' if db_role == 'client' else 'assistant'
                history.append({"role": llm_role, "content": text})
            state['conversation_history'] = history
        else:
            state['conversation_summary'] = ''
            state['conversation_history'] = []

        logger.info(
            f"Loaded context for client {client_id}: branches={sorted(b for b in branches if b)}, "
            f"history={len(state['conversation_history'])}, labs={len(state['lab_results'])}"
        )

    except Exception as e:
        logger.error(f"Error loading context: {e}")
        state['error'] = f"Ошибка загрузки контекста: {str(e)}"

    return state


def ingest_node(state: ClientState) -> ClientState:
    """
    Узел нормализации: приводит вложения к виду, понятному определителю темы.

    - Голос → текст (Whisper): metadata['audio_bytes'] = bytes,
      metadata['audio_name'] (опц.). После распознавания message_type становится 'text'.
    - Фото → тип изображения (classify_image): metadata['image_bytes'] = bytes,
      результат кладётся в state['image_kind'] ('food'|'lab_document'|'fridge'|'other'),
      чтобы тема выбиралась ПОСЛЕ распознавания содержимого, а не по модальности.
    """
    metadata = state.get('metadata') or {}

    # ── Голос → текст ───────────────────────────────────────────────────────
    if state.get('message_type') == 'voice':
        audio_bytes = metadata.get('audio_bytes')
        if audio_bytes:
            try:
                from utils.voice import transcribe_voice

                text = transcribe_voice(
                    audio_bytes,
                    file_name=metadata.get('audio_name', 'voice.ogg'),
                )
                if text:
                    state['message'] = text
                    state['message_type'] = 'text'  # дальше обрабатываем как текст
                    metadata['transcribed'] = True
                    state['metadata'] = metadata
                    logger.info(f"Transcribed voice for client {state['client_id']}: {len(text)} chars")
                else:
                    state['message'] = state.get('message', '')
                    logger.info("Voice transcription returned empty text")
            except Exception as e:
                logger.error(f"Voice transcription error: {e}")
                # Не валим обработку — пойдём дальше с исходным (возможно пустым) текстом

    # ── Фото → тип изображения (для определителя темы) ──────────────────────
    if state.get('message_type') == 'photo':
        image_bytes = metadata.get('image_bytes')
        if image_bytes:
            try:
                from utils.vision import classify_image

                state['image_kind'] = classify_image(
                    image_bytes,
                    mime_type=metadata.get('mime_type', 'image/jpeg'),
                )
                logger.info(f"Classified photo for client {state['client_id']}: {state['image_kind']}")
            except Exception as e:
                logger.warning(f"Photo classification error: {e}")
                # Без типа фото определитель/vision разрулят по умолчанию (food)

    return state


def determine_node(state: ClientState) -> ClientState:
    """
    Узел определителя темы: единый разбор хода ПОСЛЕ нормализации.

    Строит части хода (пока одна — буфер хода придёт в Фазе 2), вызывает
    intake.determine_turn → state['segments'] + state['needs_answer'].
    Решение кладётся в metadata для наблюдаемости (видно в conversations).
    """
    parts = _build_parts(state)
    result = intake.determine_turn(parts)

    state['segments'] = result['segments']
    state['needs_answer'] = result['needs_answer']

    metadata = state.get('metadata') or {}
    metadata['intake'] = {
        'segments': result['segments'],
        'needs_answer': result['needs_answer'],
    }
    state['metadata'] = metadata

    logger.info(
        f"Determined turn for client {state['client_id']}: "
        f"{[s['branch'] for s in result['segments']]} ({result['needs_answer']})"
    )
    return state


def _build_parts(state: ClientState) -> List[Dict[str, Any]]:
    """Собирает части хода для определителя (пока ход = одно сообщение)."""
    kind = state.get('message_type', 'text')
    part: Dict[str, Any] = {"kind": kind, "text": state.get('message', '') or ''}
    if kind == 'photo' and state.get('image_kind'):
        part['image_kind'] = state['image_kind']
    return [part]


# Обработчики веток. intake — по модальности (1.3 переиспользует существующие узлы;
# выделенный persist-путь intake появится в 1.4).
def _resolve_handler(state: ClientState, branch: str) -> Callable[[ClientState], ClientState]:
    if branch == ADVICE:
        return nutrition_node
    if branch == PROFILE:
        return dialog_node
    # INTAKE → по типу сообщения
    mt = state.get('message_type', 'text')
    if mt == 'photo':
        return vision_node
    if mt == 'document':
        return document_node
    return diary_node


def _dedup_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Дедуп по ВЕТКЕ: на одну ветку — один сегмент за ход (объединяем parts;
    answer побеждает ack). Порядок — по первому появлению.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for seg in segments:
        branch = seg.get('branch')
        if branch not in merged:
            merged[branch] = {
                "branch": branch,
                "parts": list(seg.get('parts') or []),
                "needs_answer": seg.get('needs_answer', ANSWER),
            }
            order.append(branch)
        else:
            m = merged[branch]
            m['parts'] = sorted(set(m['parts']) | set(seg.get('parts') or []))
            if seg.get('needs_answer') == ANSWER:
                m['needs_answer'] = ANSWER
    return [merged[b] for b in order]


def dispatch_node(state: ClientState) -> ClientState:
    """
    Узел диспетчеризации: обрабатывает каждый сегмент хода.

    - clarify — система не уверена в теме → уточняющий вопрос (обработчик не зовём).
    - intake  — обработчик вызывается ради persist + safety-алертов БЕЗ тёплого ответа
      (ack_only). Успешный захват → квитанция (под-тип); неудача → clarify с конкретным
      текстом обработчика. Данные «наугад» не пишем.
    - profile/advice — полноценный ответ обработчика.
    """
    segments = _dedup_segments(state.get('segments') or [])
    if not segments:
        segments = [{"branch": FALLBACK_BRANCH, "parts": [0], "needs_answer": CLARIFY}]

    results: List[Dict[str, Any]] = []
    used: List[str] = []
    notify = False

    for seg in segments:
        branch = seg['branch']
        needs = seg['needs_answer']

        # ── Тема не распознана → уточняющий вопрос (без обработчика) ──────────
        if needs == CLARIFY:
            results.append({
                "branch": branch, "needs_answer": CLARIFY,
                "text": _render_clarify(state), "label": "",
            })
            continue

        # ── INTAKE → persist без ответа; захват → квитанция, иначе clarify ───
        if branch == INTAKE:
            state['ack_only'] = True
            state['intake_subtype'] = None
            state['agent_response'] = ''
            _run_handler(state, branch)
            subtype = state.get('intake_subtype')
            if subtype:
                # Тёплый текст обработчика (vision — распознанный состав) выносим в ответ;
                # text-дневник оставляет его пустым → генерик-ack в format_response.
                warm = (state.get('agent_response') or '').strip()
                results.append({
                    "branch": INTAKE, "needs_answer": ACK, "text": warm,
                    "label": intake_subtype_meta(subtype).get('label_ru', label_ru(INTAKE)),
                })
            else:
                # Захват не удался → показываем конкретный уточняющий текст обработчика.
                txt = (state.get('agent_response') or '').strip() or _render_clarify(state)
                results.append({
                    "branch": INTAKE, "needs_answer": CLARIFY, "text": txt, "label": "",
                })
            used.append(state.get('agent_used') or branch)
            if (state.get('routing') or {}).get('notify_nutritionist'):
                notify = True
            continue

        # ── PROFILE / ADVICE → полноценный ответ ────────────────────────────
        state['ack_only'] = False
        state['agent_response'] = ''
        _run_handler(state, branch)
        results.append({
            "branch": branch, "needs_answer": needs,
            "text": state.get('agent_response', '') or '', "label": label_ru(branch),
        })
        used.append(state.get('agent_used') or branch)
        if (state.get('routing') or {}).get('notify_nutritionist'):
            notify = True

    state['segment_results'] = results
    state['agent_used'] = '+'.join(dict.fromkeys(u for u in used if u))
    routing = dict(state.get('routing') or {})
    routing['notify_nutritionist'] = notify
    state['routing'] = routing
    return state


def _run_handler(state: ClientState, branch: str) -> None:
    """Вызывает обработчик ветки, не роняя граф при его ошибке."""
    handler = _resolve_handler(state, branch)
    try:
        handler(state)
    except Exception as e:
        logger.error(f"Handler '{branch}' failed: {e}", exc_info=True)


def _render_clarify(state: ClientState) -> str:
    """Короткий уточняющий вопрос клиенту (дешёвый Groq; статический фолбэк)."""
    name = (state.get('client_profile') or {}).get('name') or ''
    try:
        response = call_llm(
            task_type='dialog',
            messages=[
                {"role": "system", "content": load_prompt("client/clarify_request")},
                {"role": "user", "content": f"Имя клиента: {name or 'без имени'}. "
                                            f"Сообщение: {state.get('message', '') or '—'}"},
            ],
        )
        text = (response.get('content') or '').strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"clarify render failed: {e}")
    return ("Уточни, пожалуйста: ты хочешь записать данные о дне (еда, вода, вес, самочувствие, "
            "анализы), спросить о своих показателях или попросить совет по питанию?")


def _render_ack(state: ClientState) -> str:
    """Короткое тёплое подтверждение приёма данных (дешёвый Groq; фолбэк — шаблон)."""
    name = (state.get('client_profile') or {}).get('name') or ''
    try:
        response = call_llm(
            task_type='dialog',
            messages=[
                {"role": "system", "content": load_prompt("client/ack_received")},
                {"role": "user", "content": f"Имя клиента: {name or 'без имени'}. Подтверди приём данных."},
            ],
        )
        text = (response.get('content') or '').strip()
        if text:
            return text
    except Exception as e:
        logger.warning(f"ack render failed: {e}")
    return f"Спасибо, {name}! Принято ✅" if name else "Принято ✅"


def format_response_node(state: ClientState) -> ClientState:
    """
    Узел склейки финального ответа в ОДНО сообщение.

    Порядок блоков (сверху вниз):
    1. Предупреждения безопасности + уведомление нутрициолога — через format_client_message
       (на основе alerts/routing; добавляются даже к чистому ack).
    2. Содержательная часть — тексты answer-сегментов (один без заголовка; несколько — под
       заголовками-названиями веток).
    3. Квитанция — для ack-сегментов (короткое «принято», дешёвый промпт).
    """
    from utils.helpers import format_client_message

    results = state.get('segment_results') or []
    alerts = state.get('alerts', [])
    routing = state.get('routing', {})

    clarifies = [r for r in results if r['needs_answer'] == CLARIFY and (r.get('text') or '').strip()]
    answers = [r for r in results if r['needs_answer'] == ANSWER and (r.get('text') or '').strip()]
    ack_results = [r for r in results if r['needs_answer'] == ACK]
    # Тёплый текст из ack-сегмента (vision — распознанный состав фото). text-дневник пуст.
    ack_texts = [r['text'].strip() for r in ack_results if (r.get('text') or '').strip()]

    # ── Содержательные блоки: уточнения (clarify) → ответы (answer) → тёплый ack ─
    blocks: List[str] = [c['text'].strip() for c in clarifies]
    if len(answers) == 1:
        blocks.append(answers[0]['text'].strip())
    elif len(answers) > 1:
        blocks += [f"**{a['label']}**\n{a['text'].strip()}" for a in answers]
    blocks += ack_texts

    body = "\n\n".join(blocks)

    # ── Квитанция по ack (перечень захваченных под-типов) ──────────────────
    recorded = list(dict.fromkeys(r['label'] for r in ack_results if r.get('label')))
    receipt = ("✓ Записал: " + ", ".join(recorded)) if recorded else ""

    if body:
        # Есть уточнение/ответ/тёплый ack — квитанцию просто дописываем.
        if receipt:
            body = f"{body}\n\n{receipt}"
    elif ack_results:
        # Чистый ack без тёплого текста (text-дневник) → генерик-подтверждение + квитанция.
        ack_text = _render_ack(state)
        body = f"{ack_text}\n\n{receipt}" if receipt else ack_text
    else:
        body = "Принято ✅"  # подстраховка: всё упало

    try:
        state['final_message'] = format_client_message(
            text=body,
            alerts=alerts,
            nutritionist_notified=routing.get('notify_nutritionist', False),
        )
        logger.info(f"Formatted response for client {state['client_id']}: "
                    f"clarify={len(clarifies)}, answers={len(answers)}, ack={len(ack_results)}")
    except Exception as e:
        logger.error(f"Error formatting response: {e}")
        state['final_message'] = body

    return state


def save_to_db_node(state: ClientState) -> ClientState:
    """
    Узел 5: Сохранение в БД.

    Сохраняет:
    - Сообщение пользователя в conversations
    - Ответ ассистента в conversations
    - События (если есть) в client_events
    """
    from database import queries

    client_id = state['client_id']
    channel = state['channel']
    user_message = state['message']
    assistant_message = state.get('final_message', '')

    try:
        # Сохранение сообщения пользователя.
        # Роль в БД: 'client' (constraint: client/nutritionist/agent).
        # Из metadata убираем бинарные вложения (фото/аудио), их нельзя писать в JSONB.
        queries.save_conversation(
            client_id=client_id,
            role="client",
            message_text=user_message,
            channel=channel,
            metadata={
                "message_type": state.get('message_type', 'text'),
                **_sanitize_metadata(state.get('metadata', {})),
            },
        )

        # Сохранение ответа ассистента (роль 'agent')
        queries.save_conversation(
            client_id=client_id,
            role="agent",
            message_text=assistant_message,
            channel=channel,
            metadata={
                "agent_used": state.get('agent_used'),
                "llm_model": state.get('llm_model'),
                "processing_time_ms": state.get('processing_time_ms'),
                "alerts_count": len(state.get('alerts', [])),
            },
        )

        # Примечание: структурированные события (calories_logged и т.п.) пишет сам
        # агент (например, vision_agent._log_meal_event), здесь — только диалог.

        logger.info(f"Saved conversation for client {client_id}")

    except Exception as e:
        logger.error(f"Error saving to DB: {e}")

    # Обновление скользящей сводки (best-effort, раз в N сообщений; не валит ответ)
    try:
        from .summary import update_rolling_summary
        update_rolling_summary(state)
    except Exception as e:
        logger.warning(f"Rolling summary update skipped: {e}")

    return state


def _sanitize_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Убирает из metadata бинарные/несериализуемые поля перед записью в JSONB.

    Бинарные вложения (image_bytes, audio_bytes, file_bytes) заменяются на флаг
    наличия, чтобы не ломать JSON и не раздувать таблицу.
    """
    if not metadata:
        return {}

    binary_keys = ('image_bytes', 'audio_bytes', 'file_bytes')
    cleaned: Dict[str, Any] = {}

    for key, value in metadata.items():
        if key in binary_keys:
            cleaned[f"has_{key}"] = bool(value)
        elif isinstance(value, (bytes, bytearray)):
            cleaned[f"has_{key}"] = True
        else:
            cleaned[key] = value

    return cleaned
