"""
Мультипровайдерный LLM клиент

Поддерживает переключение между провайдерами:
- Groq (llama-3.3-70b) — диалог, бесплатно
- Claude (Sonnet 4.6) — аналитика, ~$3/M токенов; серверные инструменты (web_search)
- Gemini (1.5 Flash) — vision, бесплатно

Архитектура:
1. Агент вызывает call_llm(task_type='dialog', messages=[...])
2. llm.py получает конфиг из system_settings (БД)
3. Вызывает соответствующий провайдер
4. Возвращает унифицированный ответ

Гибкость:
- Обычно: task_type → автоматический выбор модели из БД
- Эксперименты: provider+model → явное указание модели
- A/B тестирование, fallback, premium модели

TODO v1.1:
- Интеграция LangFuse для трейсинга
- Retry logic для rate limits
- Streaming support
"""

import os
import json
import time
import logging
from typing import List, Dict, Optional, Any, Tuple

try:
    import httpx  # для ListModels провайдеров (есть в зависимостях supabase)
except ImportError:
    httpx = None

# Импорты провайдеров (будут установлены через requirements.txt)
try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

# Настройка логирования
logger = logging.getLogger(__name__)


# ========================================
# КОНФИГУРАЦИЯ (Fallback маппинг)
# ========================================

DEFAULT_TASK_MODEL_MAPPING = {
    'dialog': {
        'provider': 'groq',
        'model': 'llama-3.3-70b-versatile',
        'temperature': 0.7,
        'max_tokens': 2000,
        'description': 'Ежедневный диалог с клиентом'
    },
    'analytics': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.3,
        'max_tokens': 4000,
        'description': 'Глубокий анализ данных клиента'
    },
    'vision': {
        'provider': 'gemini',
        'model': 'gemini-2.5-flash',
        'temperature': 0.5,
        'max_tokens': 1500,
        'description': 'Анализ фото еды'
    },
    'nutrition_analysis': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.4,
        'max_tokens': 3000,
        'description': 'Анализ рациона и БЖУ'
    },
    'summary': {
        'provider': 'groq',
        'model': 'llama-3.3-70b-versatile',
        'temperature': 0.5,
        'max_tokens': 2000,
        'description': 'Генерация сводок и резюме'
    },
    'planning': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.4,
        'max_tokens': 3000,
        'description': 'Создание планов питания и задач'
    },
    'orchestrator': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.4,
        'max_tokens': 2000,
        'description': 'LLM-оркестратор ветки клиента (tool-calling)'
    },
    'nutritionist_orchestrator': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.3,
        'max_tokens': 3000,
        'description': 'LLM-оркестратор ветки нутрициолога (tool-calling: аналитика + управление)'
    },
    'reminder': {
        'provider': 'groq',
        'model': 'llama-3.3-70b-versatile',
        'temperature': 0.7,
        'max_tokens': 500,
        'description': 'Тёплый текст пакета напоминаний клиенту'
    },
    'food_check': {
        # Проверка продуктов против назначений клиента (P1-13, шаг 2). На обкатке — Groq
        # (бесплатно, быстро); в рабочем режиме владелец переводит на Claude через кабинет,
        # без правки кода. temperature низкая: задача классификационная, не творческая.
        'provider': 'groq',
        'model': 'llama-3.3-70b-versatile',
        'temperature': 0.1,
        'max_tokens': 1200,
        'description': 'Смысловая проверка продуктов на аллергии/непереносимости/ограничения'
    },
    'client_audit': {
        'provider': 'claude',
        'model': 'claude-sonnet-4-6',
        'temperature': 0.3,
        'max_tokens': 1500,
        'description': 'Проактивный аудит клиента (NEW-1) — фоновая сверка 2×/нед'
    }
}


# ========================================
# TOOL-CALLING: КАКИЕ ЗАДАЧИ ЕГО ТРЕБУЮТ, КАКИЕ ПРОВАЙДЕРЫ ЕГО УМЕЮТ (P0-4)
# ========================================
# orchestrator/nutritionist_orchestrator работают через tool-calling: модель вызывает
# инструменты (log_meal, get_client_data, ...), код их выполняет и возвращает результат
# обратно (цикл tool_use → выполнение → tool_result). Ниже — только провайдеры, чей
# адаптер этот цикл реально умеет (сейчас только _call_claude); для остальных call_llm
# молча вырезает tools/tool_handlers (не умеют — не поймут). Раньше это не было явно
# сформулировано, поэтому если нутрициолог менял провайдера этих задач через кабинет —
# оркестратор продолжал отвечать текстом, но переставал что-либо записывать, без единой
# ошибки в логах (тихая потеря данных).
#
# Это НЕ жёсткая привязка к бренду Claude — это отражение того, для какого провайдера
# цикл инструментов реально написан. Добавление нового провайдера сюда — однострочное
# изменение ПОСЛЕ того, как для него появится такой же цикл в своём адаптере (см. P2-22
# в diagnostic_report.md — работа под конкретного провайдера, отдельная задача).
TOOL_CAPABLE_PROVIDERS = {'claude'}

TOOL_REQUIRED_TASK_TYPES = {'orchestrator', 'nutritionist_orchestrator'}


def validate_llm_config(value: Any) -> List[str]:
    """
    Валидация system_settings.llm_config перед сохранением (P0-4) — правило «только
    провайдер с tool-calling» для TOOL_REQUIRED_TASK_TYPES, зеркало фронтового
    validateLlmConfig (frontend/.../llmConfigValidation.ts), чтобы прямой вызов API
    не мог обойти проверку. Пусто = ок; None (сброс на код-дефолты) — тоже ок.
    """
    errors: List[str] = []
    if value is None:
        return errors
    if not isinstance(value, dict):
        return ["root: ожидается объект { task_type: {...} }"]

    for task in TOOL_REQUIRED_TASK_TYPES:
        entry = value.get(task)
        if not isinstance(entry, dict):
            continue
        provider = entry.get('provider')
        if provider not in TOOL_CAPABLE_PROVIDERS:
            errors.append(
                f"{task}.provider: должен быть одним из {sorted(TOOL_CAPABLE_PROVIDERS)} "
                f"(инструменты/tool-calling у этой задачи работают только там — другой "
                f"провайдер молча теряет все инструменты записи данных клиента)"
            )
        for i, fb in enumerate(entry.get('fallbacks') or []):
            if isinstance(fb, dict) and fb.get('provider') not in TOOL_CAPABLE_PROVIDERS:
                errors.append(
                    f"{task}.fallbacks[{i}].provider: должен быть одним из "
                    f"{sorted(TOOL_CAPABLE_PROVIDERS)}"
                )
    return errors


# ========================================
# ВЗАИМОРЕЗЕРВИРОВАНИЕ МОДЕЛЕЙ (graceful degradation)
# ========================================
# При сбое основной модели (лимиты, падение провайдера, нет кредитов) call_llm
# автоматически пробует следующие по списку — способные выполнить ту же задачу.
# Текстовые задачи резервируются бесплатными Groq/Gemini. Vision — только
# vision-моделями. Если все исчерпаны → LLMUnavailableError (просьба повторить).
TASK_FALLBACK_CHAINS = {
    'dialog': [
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    'analytics': [
        {'provider': 'groq', 'model': 'llama-3.3-70b-versatile'},
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    'nutrition_analysis': [
        {'provider': 'groq', 'model': 'llama-3.3-70b-versatile'},
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    'summary': [
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    'planning': [
        {'provider': 'groq', 'model': 'llama-3.3-70b-versatile'},
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    # vision НЕ резервируется здесь (P2-15): фото-путь идёт мимо call_llm — utils/vision.py
    # обращается к google.generativeai напрямую, поэтому цепочка отсюда никогда не читалась
    # и создавала ложное впечатление, будто резерв есть. Выбор МОДЕЛИ для vision настраивается
    # и работает (llm_config['vision']['model'] → resolve_vision_model), резерва же нет:
    # при сбое Gemini расшифровка фото деградирует штатно (оркестратор попросит уточнить).
    'vision': [],
    # Оркестратору нужен надёжный клиентский tool-calling — сейчас это только Claude.
    # Резерва в рамках LLM НЕТ: при недоступности оркестратор откатывается на граф
    # (agent_orchestrator ловит LLMUnavailableError и делегирует старому пути).
    'orchestrator': [],
    # То же для оркестратора нутрициолога — резерв = откат на граф Части B.
    'nutritionist_orchestrator': [],
    'reminder': [
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
    ],
    # Проверка продуктов: при недоступности основной модели пробуем другие. Если не вышло
    # ни одной — food_check вернёт 'unclear' (не «чисто»), см. business_rules/food_check.py.
    'food_check': [
        {'provider': 'gemini', 'model': 'gemini-2.5-flash'},
        {'provider': 'claude', 'model': 'claude-sonnet-4-6'},
    ],
}


class LLMUnavailableError(RuntimeError):
    """Все модели (основная и резервные) недоступны — нужен повтор позже."""


# ========================================
# ОСНОВНАЯ ФУНКЦИЯ (Вариант 3: гибридный)
# ========================================

def call_llm(
    messages: List[Dict[str, str]],
    task_type: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Универсальный вызов LLM с гибким управлением моделями.

    🎯 ОБЫЧНОЕ ИСПОЛЬЗОВАНИЕ (рекомендуется):
        call_llm(task_type='dialog', messages=[...])
        → Автоматически берёт конфиг из system_settings (БД)

    🧪 ЭКСПЕРИМЕНТЫ И ОСОБЫЕ СЛУЧАИ:
        call_llm(provider='openai', model='gpt-4o', messages=[...])
        → Явное указание модели (A/B тест, premium, fallback)

    Args:
        messages: Список сообщений в формате OpenAI
                  [{"role": "system|user|assistant", "content": "..."}]
        task_type: Тип задачи — 'dialog', 'analytics', 'vision',
                   'nutrition_analysis', 'summary', 'planning'
        provider: Явное указание провайдера — 'groq', 'claude', 'gemini'
        model: Явное указание модели (используется с provider)
        temperature: Температура генерации (0.0-1.0)
        max_tokens: Максимум токенов в ответе
        stream: Потоковая генерация (TODO: v1.1)
        **kwargs: Дополнительные параметры провайдера

    Returns:
        {
            "content": str,              # Сгенерированный текст
            "model": str,                # Использованная модель
            "provider": str,             # Использованный провайдер
            "usage": {
                "input_tokens": int,
                "output_tokens": int
            },
            "finish_reason": str,        # Причина остановки
            "task_type": str             # Тип задачи (если указан)
        }

    Raises:
        ValueError: Если не указан task_type или provider+model
        RuntimeError: Если провайдер недоступен или ошибка API

    Examples:
        # Обычное использование (99% случаев)
        >>> response = call_llm(
        ...     task_type='dialog',
        ...     messages=[
        ...         {"role": "system", "content": "Ты помощник нутрициолога"},
        ...         {"role": "user", "content": "Что съесть на завтрак?"}
        ...     ]
        ... )

        # Эксперимент с новой моделью
        >>> response = call_llm(
        ...     provider='claude',
        ...     model='claude-opus-4-8',
        ...     messages=[...],
        ...     temperature=0.1
        ... )

        # Переопределение температуры для task_type
        >>> response = call_llm(
        ...     task_type='analytics',
        ...     messages=[...],
        ...     temperature=0.1  # Более детерминированный анализ
        ... )
    """

    # Валидация входных данных
    if not messages or not isinstance(messages, list):
        raise ValueError("messages должен быть непустым списком")

    # Приоритет 1: Явное указание provider + model
    if provider and model:
        config = {
            'provider': provider,
            'model': model,
            'temperature': temperature if temperature is not None else 0.7,
            'max_tokens': max_tokens if max_tokens is not None else 2000
        }
        logger.info(
            f"Using explicit provider={provider}, model={model}"
        )

    # Приоритет 2: Через task_type (из system_settings или fallback)
    elif task_type:
        config = get_model_config(task_type)

        # Переопределение параметров если указаны
        if temperature is not None:
            config['temperature'] = temperature
        if max_tokens is not None:
            config['max_tokens'] = max_tokens

        logger.info(
            f"Using config for task_type='{task_type}': "
            f"{config['provider']}/{config['model']}"
        )

    else:
        raise ValueError(
            "Укажите task_type (рекомендуется) или provider+model (для экспериментов)\n"
            f"Доступные task_type: {list(DEFAULT_TASK_MODEL_MAPPING.keys())}"
        )

    # Кандидаты на выполнение: основная модель + резерв (взаимозамена).
    # Резерв подключаем только для task_type (для явного provider+model — нет,
    # там пользователь намеренно выбрал конкретную модель).
    candidates = [config]
    if task_type and not (provider and model):
        for fb in resolve_fallback_chain(task_type):
            if fb['provider'] == config['provider'] and fb['model'] == config['model']:
                continue
            candidates.append({
                'provider': fb['provider'],
                'model': fb['model'],
                'temperature': config.get('temperature', 0.7),
                'max_tokens': config.get('max_tokens', 2000),
            })

    # Обогащаем кандидатов на кастом-провайдерах base_url/api_key_env из реестра
    # (один запрос в БД, только если такие кандидаты есть).
    if any(c['provider'] not in NATIVE_PROVIDERS for c in candidates):
        custom = get_custom_providers()
        for c in candidates:
            if c['provider'] not in NATIVE_PROVIDERS and c['provider'] in custom:
                c['base_url'] = custom[c['provider']]['base_url']
                c['api_key_env'] = custom[c['provider']]['api_key_env']

    errors: List[str] = []
    for idx, cand in enumerate(candidates):
        start_time = time.monotonic()
        # tools (серверный web_search / клиентские инструменты) + tool_handlers —
        # только для провайдеров с реализованным циклом (TOOL_CAPABLE_PROVIDERS);
        # иначе убираем (эти провайдеры формат tool_use/tool_result не понимают).
        call_kwargs = dict(kwargs)
        if cand['provider'] not in TOOL_CAPABLE_PROVIDERS:
            call_kwargs.pop('tools', None)
            call_kwargs.pop('tool_handlers', None)
            call_kwargs.pop('max_tool_iterations', None)
        try:
            if cand['provider'] == 'groq':
                result = _call_groq(messages, cand, stream, **call_kwargs)
            elif cand['provider'] == 'claude':
                result = _call_claude(messages, cand, stream, **call_kwargs)
            elif cand['provider'] == 'gemini':
                result = _call_gemini(messages, cand, stream, **call_kwargs)
            elif cand.get('base_url'):
                # Кастом-провайдер (OpenAI-совместимый) из реестра _providers.
                result = _call_openai_compatible(messages, cand, stream, **call_kwargs)
            else:
                raise ValueError(
                    f"Unknown provider: {cand['provider']}. "
                    f"Нативные: groq/claude/gemini; кастом — добавьте в llm_config._providers "
                    f"(base_url + api_key_env)."
                )

            if task_type:
                result['task_type'] = task_type
            if idx > 0:
                result['fallback_used'] = True
                logger.warning(
                    f"LLM взаимозамена: задача '{task_type}' выполнена резервной "
                    f"моделью {cand['provider']}/{cand['model']} (основная не сработала)"
                )

            _trace(task_type, cand, messages, response=result, start_time=start_time)
            return result

        except Exception as e:
            _trace(task_type, cand, messages, error=str(e), start_time=start_time)
            errors.append(f"{cand['provider']}/{cand['model']}: {e}")
            logger.error(
                f"LLM call failed: provider={cand['provider']}, "
                f"model={cand['model']}, error={str(e)}"
            )
            continue

    # Все кандидаты (основная + резерв) исчерпаны — подходящей замены нет.
    raise LLMUnavailableError(
        "Все доступные модели сейчас не отвечают. "
        "Подождите немного и повторите запрос. | Детали: " + " ; ".join(errors)
    )


def _trace(
    task_type: Optional[str],
    config: Dict[str, Any],
    messages: List[Dict[str, str]],
    response: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    start_time: Optional[float] = None,
) -> None:
    """Отправляет трейс вызова в LangFuse (no-op, если трейсинг отключён)."""
    try:
        from monitoring import trace_llm_call

        latency_ms = int((time.monotonic() - start_time) * 1000) if start_time else None
        trace_llm_call(
            task_type=task_type,
            provider=config.get('provider'),
            model=config.get('model'),
            messages=messages,
            response=response,
            error=error,
            latency_ms=latency_ms,
        )
    except Exception as e:
        logger.debug(f"Трейсинг пропущен (подавлено): {e}")


def get_model_config(task_type: str) -> Dict[str, Any]:
    """
    Получает конфигурацию модели для типа задачи.

    Приоритет:
    1. Из system_settings (БД) — если настроено нутрициологом
    2. Из DEFAULT_TASK_MODEL_MAPPING (fallback)
    3. ValueError если task_type неизвестен

    Args:
        task_type: Тип задачи ('dialog', 'analytics', 'vision', ...)

    Returns:
        {
            'provider': str,
            'model': str,
            'temperature': float,
            'max_tokens': int,
            'description': str (опционально)
        }

    Raises:
        ValueError: Если task_type неизвестен
    """

    # 1. Попытка получить из system_settings (БД)
    try:
        from database import queries

        llm_config = queries.get_setting('llm_config')

        if llm_config and isinstance(llm_config, dict) and task_type in llm_config:
            # 'fallbacks' резолвится отдельно (resolve_fallback_chain) — в основной
            # конфиг модели его не пускаем, чтобы не путать вызов провайдера.
            cfg = dict(llm_config[task_type])
            cfg.pop('fallbacks', None)

            # P0-4: самолечение на случай, если в БД уже лежит непригодный провайдер
            # для tool-calling задачи (напр. записано ДО этого фикса, или save_setting
            # обойдён напрямую) — иначе оркестратор молча теряет все инструменты.
            # validate_llm_config должен был отсечь это ещё при сохранении.
            if task_type in TOOL_REQUIRED_TASK_TYPES and cfg.get('provider') not in TOOL_CAPABLE_PROVIDERS:
                logger.warning(
                    f"llm_config['{task_type}'].provider={cfg.get('provider')!r} не умеет "
                    f"tool-calling — игнорирую DB-переопределение, использую код-дефолт "
                    f"(должно быть отсечено validate_llm_config при сохранении)"
                )
            else:
                logger.info(
                    f"Loaded LLM config from system_settings for task_type='{task_type}'"
                )
                return cfg

    except ImportError:
        # database.queries ещё не готов или недоступен
        logger.debug("database.queries not available, using default mapping")

    except Exception as e:
        # Ошибка подключения к БД или получения настроек
        logger.warning(
            f"Failed to load llm_config from system_settings: {e}, "
            f"using default mapping"
        )

    # 2. Fallback на дефолтный маппинг
    if task_type in DEFAULT_TASK_MODEL_MAPPING:
        logger.info(
            f"Using default LLM config for task_type='{task_type}'"
        )
        return DEFAULT_TASK_MODEL_MAPPING[task_type].copy()

    # 3. Ошибка — неизвестный task_type
    raise ValueError(
        f"Unknown task_type: '{task_type}'. "
        f"Available: {list(DEFAULT_TASK_MODEL_MAPPING.keys())}\n"
        f"Добавьте конфигурацию в system_settings или DEFAULT_TASK_MODEL_MAPPING"
    )


def resolve_fallback_chain(task_type: str) -> List[Dict[str, str]]:
    """
    Резервная цепочка моделей для task_type. Приоритет (как у промптов):
    1. `system_settings.llm_config[task_type]['fallbacks']` (БД) — если задано нутрициологом;
    2. `TASK_FALLBACK_CHAINS` (код) — дефолт.

    Каждый элемент — {'provider': str, 'model': str}. Из БД берём цепочку, ТОЛЬКО если у
    задачи явно присутствует ключ 'fallbacks' (даже пустой список — осознанный выбор «без
    резерва»). Если задачи/ключа нет или БД недоступна — код-дефолт (прод не теряет резерв).
    """
    try:
        from database import queries

        llm_config = queries.get_setting('llm_config')
        if isinstance(llm_config, dict):
            task_cfg = llm_config.get(task_type)
            if isinstance(task_cfg, dict) and isinstance(task_cfg.get('fallbacks'), list):
                tool_required = task_type in TOOL_REQUIRED_TASK_TYPES
                chain: List[Dict[str, str]] = []
                for fb in task_cfg['fallbacks']:
                    if not (isinstance(fb, dict) and fb.get('provider') and fb.get('model')):
                        continue
                    # P0-4: самолечение — тот же принцип, что в get_model_config, чтобы
                    # резервная модель не потеряла tools молча (validate_llm_config должен
                    # был отсечь это при сохранении).
                    if tool_required and fb['provider'] not in TOOL_CAPABLE_PROVIDERS:
                        logger.warning(
                            f"resolve_fallback_chain: '{task_type}'.fallbacks содержит "
                            f"provider={fb['provider']!r} без tool-calling — пропускаю"
                        )
                        continue
                    chain.append({'provider': fb['provider'], 'model': fb['model']})
                return chain
    except Exception as e:
        logger.warning(
            f"resolve_fallback_chain: не удалось прочитать llm_config для '{task_type}', "
            f"использую код-дефолт: {e}"
        )

    return [dict(fb) for fb in TASK_FALLBACK_CHAINS.get(task_type, [])]


NATIVE_PROVIDERS = ("groq", "claude", "gemini")
"""Провайдеры со своим SDK-адаптером. Остальные — OpenAI-совместимые из реестра."""


def get_custom_providers() -> Dict[str, Dict[str, str]]:
    """
    Реестр кастом-провайдеров (OpenAI-совместимых) из `llm_config['_providers']`:
        {"<name>": {"base_url": str, "api_key_env": str}}

    Позволяет добавлять провайдеров (OpenAI / Mistral / DeepSeek / Together / …)
    КОНФИГОМ, без кода: указываешь base_url и имя env-переменной с ключом. Вызов идёт
    через generic OpenAI-совместимый адаптер. Ошибка/нет записи → {} (никогда не бросает).
    """
    try:
        from database import queries

        cfg = queries.get_setting("llm_config")
        if isinstance(cfg, dict) and isinstance(cfg.get("_providers"), dict):
            out: Dict[str, Dict[str, str]] = {}
            for name, meta in cfg["_providers"].items():
                if isinstance(meta, dict) and meta.get("base_url") and meta.get("api_key_env"):
                    out[str(name)] = {
                        "base_url": str(meta["base_url"]),
                        "api_key_env": str(meta["api_key_env"]),
                    }
            return out
    except Exception as e:
        logger.warning(f"get_custom_providers failed: {e}")
    return {}


def build_default_llm_config() -> Dict[str, Any]:
    """
    Каноничный `llm_config` из код-дефолтов: каждый task_type — основная модель
    (`DEFAULT_TASK_MODEL_MAPPING`) + вложенный резерв (`TASK_FALLBACK_CHAINS`).

    Это стартовое значение для `system_settings.llm_config` (сидер Фазы 2). Дальше
    нутрициолог правит модели через редактор «Настройки», БЕЗ кода. Источник правды
    после сидинга — БД; код-константы остаются дефолтом/фолбэком.
    """
    config: Dict[str, Any] = {}
    for task, base in DEFAULT_TASK_MODEL_MAPPING.items():
        config[task] = {
            "provider": base["provider"],
            "model": base["model"],
            "temperature": base.get("temperature", 0.7),
            "max_tokens": base.get("max_tokens", 2000),
            "fallbacks": [
                {"provider": fb["provider"], "model": fb["model"]}
                for fb in TASK_FALLBACK_CHAINS.get(task, [])
            ],
        }
    return config


# ========================================
# ОБНАРУЖЕНИЕ И ПРОВЕРКА МОДЕЛЕЙ (для окна «LLM-модели», Фаза A)
# ========================================

_MODELS_CACHE: Dict[str, Dict[str, Any]] = {}
"""provider -> {'ts': monotonic, 'models': [str]} — кэш ListModels."""

_MODELS_CACHE_TTL = 300.0
"""TTL кэша списка моделей (сек). Списки меняются редко — не дёргаем API на каждый клик."""


def list_provider_models(provider: str) -> List[str]:
    """
    Список chat/generate-моделей провайдера (живой ListModels), отфильтрованный и
    кэшированный (TTL 5 мин). Для выпадашки в окне «LLM-модели». При ошибке/без ключа/
    без httpx → [] (UI оставит ручной ввод). Никогда не бросает.
    """
    key = (provider or "").strip().lower()
    now = time.monotonic()
    cached = _MODELS_CACHE.get(key)
    if cached and now - cached["ts"] < _MODELS_CACHE_TTL:
        return cached["models"]

    try:
        if key == "groq":
            models = _list_groq_models()
        elif key == "claude":
            models = _list_claude_models()
        elif key == "gemini":
            models = _list_gemini_models()
        else:
            models = _list_openai_compatible_models(key)
    except Exception as e:
        logger.warning(f"list_provider_models({key}) failed: {e}")
        return cached["models"] if cached else []

    _MODELS_CACHE[key] = {"ts": now, "models": models}
    return models


def _list_groq_models() -> List[str]:
    """Groq (OpenAI-совместимый /models). Исключаем не-chat (whisper/tts/guard)."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key or httpx is None:
        return []
    r = httpx.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10.0,
    )
    r.raise_for_status()
    ids = [m.get("id") for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")]
    return sorted(m for m in ids if not any(x in m.lower() for x in ("whisper", "tts", "guard")))


def _list_claude_models() -> List[str]:
    """Anthropic /v1/models."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or httpx is None:
        return []
    r = httpx.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=10.0,
    )
    r.raise_for_status()
    return sorted(m.get("id") for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id"))


def _list_gemini_models() -> List[str]:
    """Gemini ListModels: только generateContent, без embedding/aqa/tts/image-генерации."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or httpx is None:
        return []
    r = httpx.get(
        f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
        timeout=10.0,
    )
    r.raise_for_status()
    out: List[str] = []
    for m in r.json().get("models", []):
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        name = (m.get("name") or "").replace("models/", "")
        if name and not any(x in name for x in ("embedding", "aqa", "tts", "image")):
            out.append(name)
    return sorted(out)


def _list_openai_compatible_models(name: str) -> List[str]:
    """Модели кастом-провайдера (OpenAI-совместимый GET {base_url}/models)."""
    meta = get_custom_providers().get(name)
    if not meta or httpx is None:
        return []
    api_key = os.environ.get(meta["api_key_env"])
    if not api_key:
        return []
    r = httpx.get(
        meta["base_url"].rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10.0,
    )
    r.raise_for_status()
    return sorted(
        m.get("id") for m in r.json().get("data", []) if isinstance(m, dict) and m.get("id")
    )


def test_model(provider: str, model: str) -> Dict[str, Any]:
    """
    Мини-пинг конкретной модели для кнопки «Проверить»: явный вызов коротким промптом
    (без резерва — проверяем ИМЕННО эту модель). Возвращает {ok, latency_ms, model, error}.
    Никогда не бросает — ошибку отдаёт в поле error.
    """
    start = time.monotonic()
    try:
        resp = call_llm(
            provider=provider,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
            temperature=0,
        )
        return {
            "ok": True,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "model": resp.get("model", model),
            "error": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "model": model,
            "error": str(e),
        }


# ========================================
# ПРИВАТНЫЕ ФУНКЦИИ ДЛЯ ПРОВАЙДЕРОВ
# ========================================

def _content_to_text(content: Any) -> str:
    """
    Приводит content к строке. Мультимодальный content (список блоков text/image —
    формат Claude) не поддерживается не-Claude провайдерами: берём только текстовые блоки,
    image-блоки помечаем плейсхолдером. Так стороний ход с картинкой не роняет groq/gemini/
    openai-совместимые (в проде фото идёт только в Claude, но это защита от будущих путей).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
            elif block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "image":
                parts.append("[изображение]")
        return "\n".join(p for p in parts if p)
    return "" if content is None else str(content)


def _flatten_content(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Копия messages со строковым content (для провайдеров без мультимодальности)."""
    return [{**m, "content": _content_to_text(m.get("content"))} for m in messages]


def _call_groq(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Вызов Groq API (llama-3.3-70b).

    Используется для:
    - Ежедневный диалог (быстро, бесплатно)
    - Генерация сводок
    """
    if Groq is None:
        raise RuntimeError(
            "Groq SDK не установлен. Установите: pip install groq"
        )

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY не найден в переменных окружения. "
            "Добавьте в .env или Render Environment Variables"
        )

    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model=config['model'],
            messages=_flatten_content(messages),
            temperature=config['temperature'],
            max_tokens=config['max_tokens'],
            stream=stream,
            **kwargs
        )

        if stream:
            # TODO v1.1: Поддержка streaming
            logger.warning("Streaming not fully implemented for Groq")
            return response

        return {
            'content': response.choices[0].message.content,
            'model': config['model'],
            'provider': 'groq',
            'usage': {
                'input_tokens': response.usage.prompt_tokens,
                'output_tokens': response.usage.completion_tokens,
                'total_tokens': response.usage.total_tokens
            },
            'finish_reason': normalize_finish_reason(response.choices[0].finish_reason)
        }

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        raise


def _call_openai_compatible(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Generic-адаптер для OpenAI-совместимых провайдеров (OpenAI/Mistral/DeepSeek/…).

    base_url и имя env-ключа берутся из config (обогащено call_llm из реестра
    llm_config._providers). Контракт ответа — как у нативных адаптеров.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai SDK не установлен. Установите: pip install openai")

    base_url = config.get('base_url')
    api_key_env = config.get('api_key_env')
    provider_name = config.get('provider', 'custom')
    if not base_url or not api_key_env:
        raise RuntimeError(
            f"Кастом-провайдер '{provider_name}' без base_url/api_key_env "
            f"(добавьте в llm_config._providers)"
        )

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{api_key_env} не задан в окружении (ключ провайдера '{provider_name}')"
        )

    try:
        client = OpenAI(base_url=base_url, api_key=api_key)
        response = client.chat.completions.create(
            model=config['model'],
            messages=_flatten_content(messages),
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 2000),
            stream=stream,
            **kwargs
        )
        if stream:
            logger.warning("Streaming not fully implemented for OpenAI-compatible")
            return response

        usage = response.usage
        return {
            'content': response.choices[0].message.content,
            'model': config['model'],
            'provider': provider_name,
            'usage': {
                'input_tokens': getattr(usage, 'prompt_tokens', 0) if usage else 0,
                'output_tokens': getattr(usage, 'completion_tokens', 0) if usage else 0,
                'total_tokens': getattr(usage, 'total_tokens', 0) if usage else 0,
            },
            'finish_reason': normalize_finish_reason(response.choices[0].finish_reason),
        }
    except Exception as e:
        logger.error(f"OpenAI-compatible ({provider_name}) API error: {e}")
        raise


def _run_client_tools(
    content_blocks: List[Any],
    tool_handlers: Dict[str, Any],
    trace: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Выполняет клиентские инструменты из ответа Claude (блоки type='tool_use')
    и собирает блоки tool_result для дослания модели.

    tool_handlers: {имя_инструмента: callable(input_dict) -> str | JSON-сериализуемое}.
    Ошибка/отсутствие обработчика не роняет вызов — возвращается tool_result с
    is_error=True, чтобы модель могла восстановиться (переспросить/выбрать другой путь).
    trace пополняется записями {name, input, is_error} для наблюдаемости/трейсинга.
    """
    tool_results: List[Dict[str, Any]] = []
    for block in content_blocks:
        if getattr(block, 'type', None) != 'tool_use':
            continue
        name = getattr(block, 'name', '')
        tool_input = getattr(block, 'input', None) or {}
        is_error = False
        try:
            handler = tool_handlers.get(name)
            if handler is None:
                result_str = f"Ошибка: инструмент '{name}' не зарегистрирован."
                is_error = True
            else:
                result = handler(tool_input)
                result_str = result if isinstance(result, str) else json.dumps(
                    result, ensure_ascii=False, default=str
                )
        except Exception as e:  # noqa: BLE001 — ошибку инструмента отдаём модели, не роняем ход
            logger.error(f"Client tool '{name}' failed: {e}", exc_info=True)
            result_str = f"Ошибка инструмента: {e}"
            is_error = True

        trace.append({'name': name, 'input': tool_input, 'is_error': is_error})
        tool_result: Dict[str, Any] = {
            'type': 'tool_result',
            'tool_use_id': getattr(block, 'id', None),
            'content': result_str,
        }
        if is_error:
            tool_result['is_error'] = True
        tool_results.append(tool_result)

    return tool_results


def _call_claude(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Вызов Claude API (Anthropic).

    Используется для:
    - Аналитика (глубокий анализ, ~$3/M токенов)
    - Анализ рациона
    - Создание планов питания
    """
    if Anthropic is None:
        raise RuntimeError(
            "Anthropic SDK не установлен. Установите: pip install anthropic"
        )

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY не найден в переменных окружения"
        )

    try:
        client = Anthropic(api_key=api_key)

        # Claude требует system сообщение отдельно
        system_message = None
        claude_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                claude_messages.append({
                    'role': msg['role'],
                    'content': msg['content']
                })

        if stream:
            # TODO v1.1: Поддержка streaming
            logger.warning("Streaming not fully implemented for Claude")
            return client.messages.create(
                model=config['model'],
                system=system_message,
                messages=claude_messages,
                temperature=config['temperature'],
                max_tokens=config['max_tokens'],
                stream=True,
                **kwargs
            )

        # Инструменты передаются через tools (Anthropic-схема). Два вида:
        #  • СЕРВЕРНЫЕ (web_search) — Anthropic выполняет сам; возможен
        #    stop_reason='pause_turn' → дослать ассистентский ход и продолжить.
        #  • КЛИЕНТСКИЕ — модель возвращает stop_reason='tool_use' с блоками tool_use;
        #    ИХ выполняем МЫ через tool_handlers[name](input) и возвращаем tool_result.
        # tool_handlers / max_tool_iterations — наши параметры, НЕ параметры Anthropic:
        # изымаем из kwargs до вызова .create().
        tool_handlers = kwargs.pop('tool_handlers', None)
        max_iterations = kwargs.pop('max_tool_iterations', 8)

        tool_calls_trace: List[Dict[str, Any]] = []
        total_input = 0
        total_output = 0
        web_search_requests = 0

        loop_messages = list(claude_messages)
        response = None
        for _ in range(max_iterations):
            response = client.messages.create(
                model=config['model'],
                system=system_message,
                messages=loop_messages,
                temperature=config['temperature'],
                max_tokens=config['max_tokens'],
                stream=False,
                **kwargs
            )

            # Накапливаем usage по всем итерациям цикла инструментов.
            total_input += response.usage.input_tokens
            total_output += response.usage.output_tokens
            server_tool_use = getattr(response.usage, 'server_tool_use', None)
            if server_tool_use is not None:
                wr = getattr(server_tool_use, 'web_search_requests', None)
                if wr:
                    web_search_requests += wr

            stop = response.stop_reason

            # Серверный инструмент приостановил ход — дослать ассистентский ход.
            if stop == 'pause_turn':
                loop_messages.append({'role': 'assistant', 'content': response.content})
                continue

            # Клиентские инструменты — выполняем и возвращаем результаты.
            if stop == 'tool_use' and tool_handlers:
                tool_results = _run_client_tools(response.content, tool_handlers, tool_calls_trace)
                loop_messages.append({'role': 'assistant', 'content': response.content})
                loop_messages.append({'role': 'user', 'content': tool_results})
                continue

            # Обычное завершение (end_turn / max_tokens / stop_sequence),
            # либо tool_use без переданных обработчиков — выходим.
            break
        else:
            logger.warning(
                f"Claude tool loop hit max_iterations={max_iterations}"
            )

        # Финальный текст собираем из всех text-блоков (перед ним могут идти
        # блоки server_tool_use / web_search_tool_result / tool_use).
        content_text = "".join(
            block.text for block in response.content
            if getattr(block, 'type', None) == 'text'
        )

        usage = {
            'input_tokens': total_input,
            'output_tokens': total_output,
            'total_tokens': total_input + total_output,
        }
        if web_search_requests:
            usage['web_search_requests'] = web_search_requests

        result = {
            'content': content_text,
            'model': config['model'],
            'provider': 'claude',
            'usage': usage,
            'finish_reason': normalize_finish_reason(response.stop_reason),
        }
        if tool_calls_trace:
            result['tool_calls'] = tool_calls_trace
        return result

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


# ────────────────────────────────────────────────────────────────────────────
# УНИФИКАЦИЯ finish_reason (P2-15)
# ────────────────────────────────────────────────────────────────────────────
# Каждый провайдер называет причину остановки по-своему: OpenAI/Groq — 'stop'/'length',
# Anthropic — 'end_turn'/'max_tokens', Gemini — 'STOP'/'MAX_TOKENS'. Вызывающий код не мог
# надёжно понять «ответ оборван по лимиту» — а это важно: обрезанный JSON или обрезанный
# совет клиенту выглядят как валидный результат. Приводим к общему словарю.
#
# Значения: 'stop' — договорил; 'length' — упёрся в лимит токенов; 'tool_use' — просит
# инструмент; 'filter' — отфильтровано провайдером; 'other' — всё прочее/неизвестное.
_FINISH_REASON_MAP = {
    # OpenAI / Groq
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_use",
    "content_filter": "filter",
    # Anthropic
    "end_turn": "stop",
    "max_tokens": "length",
    "stop_sequence": "stop",
    "tool_use": "tool_use",
    "refusal": "filter",
    # Gemini (enum .name)
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "filter",
    "RECITATION": "filter",
    "PROHIBITED_CONTENT": "filter",
    "BLOCKLIST": "filter",
}


def normalize_finish_reason(raw: Any) -> str:
    """Причина остановки в общем словаре (см. _FINISH_REASON_MAP). Неизвестное → 'other'."""
    if raw is None:
        return "other"
    return _FINISH_REASON_MAP.get(str(raw), "other")


def _gemini_payload(messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Готовит сообщения под Gemini: (system_instruction, contents).

    P2-15: раньше system и user оба маппились в роль 'user', и типичный набор
    [system, user] превращался в два 'user' подряд. Gemini требует СТРОГОГО чередования
    user/model и на таком входе отвечает 400 — то есть резервная цепочка ломалась ровно
    тогда, когда была нужна (основная модель уже упала). Теперь:
      • system-сообщения уходят в system_instruction (штатное место для них);
      • подряд идущие сообщения одной роли склеиваются, чтобы чередование не нарушалось.
    """
    system_parts = [
        _content_to_text(m["content"]) for m in messages if m.get("role") == "system"
    ]
    contents: List[Dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            continue
        role = "model" if msg.get("role") == "assistant" else "user"
        text = _content_to_text(msg.get("content"))
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0] = f"{contents[-1]['parts'][0]}\n\n{text}"
        else:
            contents.append({"role": role, "parts": [text]})

    system_instruction = "\n\n".join(p for p in system_parts if p) or None
    return system_instruction, contents


def _call_gemini(
    messages: List[Dict[str, str]],
    config: Dict[str, Any],
    stream: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Вызов Gemini API (Google).

    Используется для:
    - Vision (анализ фото еды, бесплатно 1500 req/день)
    - Быстрая генерация
    """
    if genai is None:
        raise RuntimeError(
            "Google Generative AI SDK не установлен. "
            "Установите: pip install google-generativeai"
        )

    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY не найден в переменных окружения"
        )

    try:
        genai.configure(api_key=api_key)

        # P2-15: system уходит отдельным параметром, роли чередуются корректно.
        system_instruction, gemini_messages = _gemini_payload(messages)
        model = (
            genai.GenerativeModel(config['model'], system_instruction=system_instruction)
            if system_instruction
            else genai.GenerativeModel(config['model'])
        )

        # Вызов API
        response = model.generate_content(
            gemini_messages,
            generation_config={
                'temperature': config['temperature'],
                'max_output_tokens': config['max_tokens']
            },
            stream=stream,
            **kwargs
        )

        if stream:
            # TODO v1.1: Поддержка streaming
            logger.warning("Streaming not fully implemented for Gemini")
            return response

        return {
            'content': response.text,
            'model': config['model'],
            'provider': 'gemini',
            'usage': {
                'input_tokens': response.usage_metadata.prompt_token_count,
                'output_tokens': response.usage_metadata.candidates_token_count,
                'total_tokens': response.usage_metadata.total_token_count
            },
            'finish_reason': normalize_finish_reason(response.candidates[0].finish_reason.name)
        }

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise


# ========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def list_available_providers() -> List[str]:
    """
    Возвращает список доступных провайдеров.
    Проверяет наличие SDK и API ключей.
    """
    available = []

    if Groq and os.environ.get('GROQ_API_KEY'):
        available.append('groq')

    if Anthropic and os.environ.get('ANTHROPIC_API_KEY'):
        available.append('claude')

    if genai and os.environ.get('GOOGLE_API_KEY'):
        available.append('gemini')

    # Кастом-провайдеры (OpenAI-совместимые) — доступны, если задан их env-ключ.
    for name, meta in get_custom_providers().items():
        if os.environ.get(meta['api_key_env']):
            available.append(name)

    return available


def list_task_types() -> Dict[str, str]:
    """
    Возвращает список доступных task_type с описаниями.
    Используется для UI нутрициолога.
    """
    return {
        task: config.get('description', 'Нет описания')
        for task, config in DEFAULT_TASK_MODEL_MAPPING.items()
    }


# ========================================
# ТРЕЙСИНГ LANGFUSE
# ========================================
# Реализован в monitoring/langfuse.py и подключён выше через _trace() в call_llm.
# Все вызовы LLM (все агенты) трейсятся автоматически. Трейсинг — no-op без ключей.
