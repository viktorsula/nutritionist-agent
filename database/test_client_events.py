"""
Тесты database/queries.py — get_client_events (фильтр event_type, P1-5/P1-9) и
has_event_today (персистентный дедуп алертов, P1: no_response спам).
"""

from unittest.mock import patch

from database import queries


def _base_chain(mock_client):
    """.table().select().eq("client_id",...).order().limit() — общий префикс запроса."""
    return (
        mock_client.return_value.table.return_value.select.return_value
        .eq.return_value.order.return_value.limit.return_value
    )


def test_get_client_events_filters_by_event_type_when_given():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_client_events("c1", event_type="no_response")

    base = _base_chain(mock_client)
    base.eq.assert_called_once_with("event_type", "no_response")


def test_get_client_events_no_event_type_filter_when_omitted():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_client_events("c1")

    base = _base_chain(mock_client)
    base.eq.assert_not_called()
    base.execute.assert_called_once()


def test_get_client_events_combines_severity_and_event_type():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_client_events("c1", severity="high", event_type="weight_increase")

    base = _base_chain(mock_client)
    base.eq.assert_called_once_with("severity", "high")
    base.eq.return_value.eq.assert_called_once_with("event_type", "weight_increase")
    base.eq.return_value.eq.return_value.execute.assert_called_once()


def test_has_event_today_true_when_rows_found():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[{"id": "e1"}]):
        result = queries.has_event_today("c1", "no_response", "2026-07-25")
    assert result is True

    table = mock_client.return_value.table
    table.assert_called_once_with("client_events")
    gte_call = table.return_value.select.return_value.eq.return_value.eq.return_value.gte
    gte_call.assert_called_once_with("event_date", "2026-07-25T00:00:00")


def test_has_event_today_false_when_no_rows():
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=[]):
        result = queries.has_event_today("c1", "no_response", "2026-07-25")
    assert result is False
