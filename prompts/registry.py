"""
Реестр промптов — единая точка правды для редактора в «Настройках».

Каждый промпт описан понятным названием (RU/EN) и отнесён к разделу:
- "communication" — влияет на общение с клиентом и работу нутрициолога;
  нутрициолог правит его сам через веб-редактор.
- "system" — технические/фоновые промпты (классификаторы, парсеры, vision,
  разбор команд); правит только разработчик. В веб-редакторе показываются
  read-only (нутрициолог видит, но не меняет).

Ключ (`key`) — это имя для load_prompt() и для system_settings.prompts (БД-override),
оно же путь к .md-файлу (без расширения). Названия в коде НЕ используются — только
понятные подписи для интерфейса.
"""

from typing import Any, Dict, List

SECTION_COMMUNICATION = "communication"
SECTION_SYSTEM = "system"

# Порядок записей сохраняется в интерфейсе.
PROMPTS: List[Dict[str, str]] = [
    # ── Коммуникационные (правит нутрициолог) ───────────────────────────────
    {
        "key": "client/orchestrator_system",
        "label_ru": "Оркестратор клиента (главный промпт)",
        "label_en": "Client orchestrator (main)",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "client/dialog_system",
        "label_ru": "Диалог с клиентом",
        "label_en": "Client dialog",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    {
        "key": "client/diary_system",
        "label_ru": "Ответ на дневник",
        "label_en": "Diary reply",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    {
        "key": "client/nutrition_system",
        "label_ru": "Ответ про питание",
        "label_en": "Nutrition answer",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "client/vision_system",
        "label_ru": "Ответ на фото еды",
        "label_en": "Food photo reply",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    {
        "key": "client/reminder_message",
        "label_ru": "Текст напоминания клиенту",
        "label_en": "Client reminder message",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    {
        "key": "nutritionist/orchestrator_system",
        "label_ru": "Оркестратор нутрициолога (главный промпт)",
        "label_en": "Nutritionist orchestrator (main)",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "nutritionist/analytics_system",
        "label_ru": "Аналитика для нутрициолога",
        "label_en": "Analytics report",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "nutritionist/reports/recommendations_for_clients",
        "label_ru": "Шаблон отчёта по клиенту",
        "label_en": "Client report template",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "nutritionist/reports/recommendations_system",
        "label_ru": "Правила генерации отчёта",
        "label_en": "Report generation rules",
        "section": SECTION_COMMUNICATION,
        "llm": "Claude",
    },
    {
        "key": "client/ack_received",
        "label_ru": "Подтверждение получения («Принято»)",
        "label_en": "Receipt acknowledgement",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    {
        "key": "client/clarify_request",
        "label_ru": "Уточняющий вопрос клиенту",
        "label_en": "Clarifying question",
        "section": SECTION_COMMUNICATION,
        "llm": "Groq",
    },
    # ── Системные (правит разработчик; read-only для нутрициолога) ───────────
    {
        "key": "nutritionist/management_system",
        "label_ru": "Разбор команд нутрициолога",
        "label_en": "Command parser",
        "section": SECTION_SYSTEM,
        "llm": "Claude",
    },
    {
        "key": "system/intake_determiner",
        "label_ru": "Определитель темы сообщения",
        "label_en": "Intake topic determiner",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/client_router",
        "label_ru": "Маршрутизация сообщений клиента",
        "label_en": "Client message router",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/diary_extraction",
        "label_ru": "Извлечение данных из дневника",
        "label_en": "Diary data extraction",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/questionnaire_summary",
        "label_ru": "Саммари анкеты онбординга",
        "label_en": "Onboarding questionnaire summary",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/client_summary",
        "label_ru": "Сводка диалога (память)",
        "label_en": "Conversation summary",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/vision_food_plate",
        "label_ru": "Распознавание блюда (фото)",
        "label_en": "Food plate analysis",
        "section": SECTION_SYSTEM,
        "llm": "Gemini",
    },
    {
        "key": "system/vision_image_kind",
        "label_ru": "Определение типа фото",
        "label_en": "Image type detection",
        "section": SECTION_SYSTEM,
        "llm": "Gemini",
    },
    {
        "key": "system/vision_lab_document",
        "label_ru": "Распознавание анализов (фото)",
        "label_en": "Lab photo recognition",
        "section": SECTION_SYSTEM,
        "llm": "Gemini",
    },
    {
        "key": "system/vision_fridge",
        "label_ru": "Распознавание продуктов (холодильник)",
        "label_en": "Fridge products recognition",
        "section": SECTION_SYSTEM,
        "llm": "Gemini",
    },
    {
        "key": "system/labs_extraction",
        "label_ru": "Извлечение анализов из текста",
        "label_en": "Lab text extraction",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/nutritionist_router",
        "label_ru": "Маршрутизация запросов нутрициолога",
        "label_en": "Nutritionist request router",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
    {
        "key": "system/analytics_plan",
        "label_ru": "План аналитики",
        "label_en": "Analytics planning",
        "section": SECTION_SYSTEM,
        "llm": "Groq",
    },
]

_BY_KEY = {p["key"]: p for p in PROMPTS}


def prompt_registry() -> List[Dict[str, str]]:
    """Полный реестр промптов (копия, порядок сохранён)."""
    return [dict(p) for p in PROMPTS]


def get_prompt_meta(key: str) -> Dict[str, str]:
    """Метаданные промпта по ключу ({} если неизвестен)."""
    return dict(_BY_KEY.get(key, {}))


def is_editable(key: str) -> bool:
    """True, если промпт известен реестру и его можно править через веб.

    Раньше правились только communication; теперь и системные промпты доступны
    нутрициологу через веб-редактор (с предупреждением). Откат прост: удалить override
    в system_settings.prompts → вернётся дефолт из .md. Неизвестные ключи — не редактируемы.
    """
    return key in _BY_KEY


def list_prompts_with_meta() -> List[Dict[str, Any]]:
    """
    Реестр + источник текущего значения каждого промпта.

    source: 'db' — переопределён нутрициологом в system_settings.prompts;
            'file' — используется дефолт из .md.
    editable: можно ли менять через веб (теперь — все известные промпты).
    section: 'communication' | 'system' — для группировки по вкладкам в редакторе.
    """
    overrides: Dict[str, Any] = {}
    try:
        from database import queries

        overrides = queries.get_setting("prompts") or {}
    except Exception:
        overrides = {}

    result: List[Dict[str, Any]] = []
    for p in PROMPTS:
        entry = dict(p)
        entry["source"] = "db" if p["key"] in overrides else "file"
        entry["editable"] = True
        result.append(entry)
    return result
