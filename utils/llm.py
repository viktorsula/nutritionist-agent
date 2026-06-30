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
import time
import logging
from typing import List, Dict, Optional, Any

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
    }
}


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
    'vision': [
        # vision умеют Claude и Gemini; Groq — нет, поэтому в резерве только Claude.
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
        for fb in TASK_FALLBACK_CHAINS.get(task_type, []):
            if fb['provider'] == config['provider'] and fb['model'] == config['model']:
                continue
            candidates.append({
                'provider': fb['provider'],
                'model': fb['model'],
                'temperature': config.get('temperature', 0.7),
                'max_tokens': config.get('max_tokens', 2000),
            })

    errors: List[str] = []
    for idx, cand in enumerate(candidates):
        start_time = time.monotonic()
        # tools (серверный web_search) — только для Claude; иначе убираем.
        call_kwargs = dict(kwargs)
        if cand['provider'] != 'claude':
            call_kwargs.pop('tools', None)
        try:
            if cand['provider'] == 'groq':
                result = _call_groq(messages, cand, stream, **call_kwargs)
            elif cand['provider'] == 'claude':
                result = _call_claude(messages, cand, stream, **call_kwargs)
            elif cand['provider'] == 'gemini':
                result = _call_gemini(messages, cand, stream, **call_kwargs)
            else:
                raise ValueError(
                    f"Unknown provider: {cand['provider']}. Supported: groq, claude, gemini"
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
            logger.info(
                f"Loaded LLM config from system_settings for task_type='{task_type}'"
            )
            return llm_config[task_type]

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


# ========================================
# ПРИВАТНЫЕ ФУНКЦИИ ДЛЯ ПРОВАЙДЕРОВ
# ========================================

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
            messages=messages,
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
            'finish_reason': response.choices[0].finish_reason
        }

    except Exception as e:
        logger.error(f"Groq API error: {e}")
        raise


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

        # Серверные инструменты (например, web_search) передаются через tools.
        # Anthropic сам выполняет поиск; при server-tool-цикле возможен
        # stop_reason='pause_turn' — нужно дослать ответ и продолжить.
        # max_iterations — предохранитель от бесконечного цикла.
        max_iterations = 5
        loop_messages = claude_messages
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

            if response.stop_reason != 'pause_turn':
                break

            # Сервер приостановил server-tool-цикл — дослать ассистентский ход
            # и продолжить (без дополнительного user-сообщения).
            loop_messages = loop_messages + [
                {'role': 'assistant', 'content': response.content}
            ]
        else:
            logger.warning(
                f"Claude server-tool loop hit max_iterations={max_iterations}"
            )

        # Финальный текст собираем из всех text-блоков (перед ним могут идти
        # блоки server_tool_use / web_search_tool_result).
        content_text = "".join(
            block.text for block in response.content
            if getattr(block, 'type', None) == 'text'
        )

        usage = {
            'input_tokens': response.usage.input_tokens,
            'output_tokens': response.usage.output_tokens,
            'total_tokens': response.usage.input_tokens + response.usage.output_tokens
        }
        # Учёт серверных инструментов (web search) для стоимости/трейсинга.
        server_tool_use = getattr(response.usage, 'server_tool_use', None)
        if server_tool_use is not None:
            web_requests = getattr(server_tool_use, 'web_search_requests', None)
            if web_requests is not None:
                usage['web_search_requests'] = web_requests

        return {
            'content': content_text,
            'model': config['model'],
            'provider': 'claude',
            'usage': usage,
            'finish_reason': response.stop_reason
        }

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


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
        model = genai.GenerativeModel(config['model'])

        # Конвертация формата сообщений для Gemini
        # Gemini использует 'user' и 'model' (не 'assistant')
        gemini_messages = []
        for msg in messages:
            role = 'user' if msg['role'] in ['user', 'system'] else 'model'
            gemini_messages.append({
                'role': role,
                'parts': [msg['content']]
            })

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
            'finish_reason': response.candidates[0].finish_reason.name
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
