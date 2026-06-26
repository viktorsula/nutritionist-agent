"""
Система управления промптами для агентов

Архитектура (3 уровня):
1. MVP: Промпты в .md файлах
2. v1.1: Редактирование через БД (system_settings.prompts)
3. v1.1+: Веб-интерфейс в Streamlit

Приоритет источников:
1. БД (system_settings.prompts) — если настроено нутрициологом
2. Файлы .md (fallback) — дефолтные версии
"""

import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def load_prompt(prompt_name: str, version: str = 'current') -> str:
    """
    Загружает промпт с приоритетом источников.

    Приоритет:
    1. Из БД (system_settings.prompts) — если настроено
    2. Из файла .md (fallback)

    Args:
        prompt_name: Имя промпта ('client/dialog_system')
        version: Версия ('current', 'v1', 'v2') для A/B тестов

    Returns:
        Текст промпта

    Raises:
        ValueError: Если промпт не найден

    Example:
        >>> template = load_prompt('client/dialog_system')
        >>> prompt = template.format(client_name='Мария', ...)
    """

    # Приоритет 1: Попытка загрузить из БД
    try:
        from database import queries

        prompts_config = queries.get_setting('prompts')

        if prompts_config and prompt_name in prompts_config:
            prompt_data = prompts_config[prompt_name]

            # Если указана конкретная версия
            if version != 'current' and 'versions' in prompt_data:
                if version in prompt_data['versions']:
                    logger.info(f"Loaded prompt '{prompt_name}' version '{version}' from DB")
                    return prompt_data['versions'][version]

            # Текущая версия
            if 'current' in prompt_data:
                logger.info(f"Loaded prompt '{prompt_name}' from DB")
                return prompt_data['current']

            if 'text' in prompt_data:
                logger.info(f"Loaded prompt '{prompt_name}' from DB (legacy format)")
                return prompt_data['text']

    except ImportError:
        logger.debug("database.queries not available, using file fallback")

    except Exception as e:
        logger.warning(f"Failed to load prompt from DB: {e}, using file fallback")

    # Приоритет 2: Загрузка из файла (fallback)
    file_path = os.path.join(
        os.path.dirname(__file__),
        f"{prompt_name}.md"
    )

    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            logger.info(f"Loaded prompt '{prompt_name}' from file")
            return content

    # Не найден
    raise ValueError(
        f"Prompt not found: '{prompt_name}'\n"
        f"Searched in:\n"
        f"  - system_settings.prompts (DB)\n"
        f"  - {file_path}"
    )


def save_prompt(
    prompt_name: str,
    text: str,
    version: Optional[str] = None,
    description: Optional[str] = None
) -> None:
    """
    Сохраняет промпт в БД (для веб-интерфейса).

    Args:
        prompt_name: Имя промпта
        text: Текст промпта
        version: Версия (опционально, для A/B тестов)
        description: Описание изменений

    Example:
        >>> save_prompt(
        ...     'client/dialog_system',
        ...     'Новый текст промпта',
        ...     version='v2',
        ...     description='Добавлена поддержка арабского языка'
        ... )
    """
    from database import queries
    import datetime

    prompts_config = queries.get_setting('prompts') or {}

    if prompt_name not in prompts_config:
        prompts_config[prompt_name] = {
            'current': text,
            'versions': {},
            'history': []
        }
    else:
        if version:
            # Сохранить как версию (для A/B тестов)
            if 'versions' not in prompts_config[prompt_name]:
                prompts_config[prompt_name]['versions'] = {}

            prompts_config[prompt_name]['versions'][version] = text
        else:
            # Обновить текущую версию
            # Сохранить предыдущую в истории
            if 'history' not in prompts_config[prompt_name]:
                prompts_config[prompt_name]['history'] = []

            prompts_config[prompt_name]['history'].append({
                'text': prompts_config[prompt_name].get('current'),
                'timestamp': datetime.datetime.now().isoformat(),
                'description': description or 'Previous version'
            })

            prompts_config[prompt_name]['current'] = text

    # Сохранить в system_settings
    queries.update_system_setting(
        key='prompts',
        value=prompts_config,
        updated_by='nutritionist'  # TODO: Получать из сессии
    )

    logger.info(f"Saved prompt '{prompt_name}' to DB" + (f" as version '{version}'" if version else ""))


def list_available_prompts() -> Dict[str, Any]:
    """
    Возвращает список всех доступных промптов.

    Returns:
        {
            'client/dialog_system': {
                'source': 'db' | 'file',
                'has_versions': bool,
                'versions': [...],
                'file_path': str
            },
            ...
        }
    """
    prompts = {}

    # Сканирование файлов
    prompts_dir = os.path.dirname(__file__)
    for root, dirs, files in os.walk(prompts_dir):
        for file in files:
            if file.endswith('.md'):
                rel_path = os.path.relpath(
                    os.path.join(root, file),
                    prompts_dir
                )
                prompt_name = rel_path.replace('.md', '').replace(os.sep, '/')

                prompts[prompt_name] = {
                    'source': 'file',
                    'has_versions': False,
                    'versions': [],
                    'file_path': rel_path
                }

    # Проверка БД
    try:
        from database import queries

        prompts_config = queries.get_setting('prompts') or {}

        for prompt_name, data in prompts_config.items():
            if prompt_name not in prompts:
                prompts[prompt_name] = {
                    'source': 'db',
                    'has_versions': False,
                    'versions': [],
                    'file_path': None
                }
            else:
                prompts[prompt_name]['source'] = 'db'  # БД имеет приоритет

            if 'versions' in data and data['versions']:
                prompts[prompt_name]['has_versions'] = True
                prompts[prompt_name]['versions'] = list(data['versions'].keys())

    except Exception as e:
        logger.debug(f"Could not check DB for prompts: {e}")

    return prompts


def get_prompt_history(prompt_name: str) -> list:
    """
    Получает историю изменений промпта.

    Args:
        prompt_name: Имя промпта

    Returns:
        [
            {
                'text': str,
                'timestamp': str,
                'description': str
            },
            ...
        ]
    """
    try:
        from database import queries

        prompts_config = queries.get_setting('prompts') or {}

        if prompt_name in prompts_config:
            return prompts_config[prompt_name].get('history', [])

    except Exception as e:
        logger.warning(f"Failed to get prompt history: {e}")

    return []


from prompts.registry import (
    prompt_registry,
    get_prompt_meta,
    is_editable,
    list_prompts_with_meta,
)

__all__ = [
    'load_prompt',
    'save_prompt',
    'list_available_prompts',
    'get_prompt_history',
    'prompt_registry',
    'get_prompt_meta',
    'is_editable',
    'list_prompts_with_meta',
]
