"""
Тест get_setting: читает колонку JSONB `value` (а не несуществующую `setting_value`).

Регрессия: ранее `get_setting` читал `setting.get('setting_value')` → всегда None →
БД-переопределение моделей/промптов/trusted_sources было мёртвым (маскировалось
код-дефолтами/файлами). Колонка в schema.sql — `value`, писатели пишут в `value`.
"""

from unittest.mock import patch

from database.queries import get_setting


def test_get_setting_reads_value_column():
    row = {"key": "llm_config", "value": {"dialog": {"provider": "groq"}}, "description": None}
    with patch("database.queries.get_system_setting", return_value=row):
        assert get_setting("llm_config") == {"dialog": {"provider": "groq"}}


def test_get_setting_none_when_absent():
    with patch("database.queries.get_system_setting", return_value=None):
        assert get_setting("llm_config") is None
