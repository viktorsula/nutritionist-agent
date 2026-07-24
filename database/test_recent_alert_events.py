"""
get_recent_alert_events: whitelist event_type для гарантированного Telegram-пуша
нутрициологу независимо от severity (миграция 017 — добавлен questionnaire_updated,
решение владельца: "нутрициолог обязательно узнаёт об изменении анкеты").
"""

from unittest.mock import patch

from database import queries


def test_whitelist_includes_questionnaire_updated():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_recent_alert_events(5)

    or_call = mock_client.return_value.table.return_value.select.return_value.gte.return_value.or_
    filter_str = or_call.call_args.args[0]
    assert "questionnaire_updated" in filter_str
    # Существующие типы не должны потеряться при добавлении нового.
    assert "bad_wellbeing" in filter_str
    assert "meal_not_reported" in filter_str
    assert "severity.in.(high,critical)" in filter_str
