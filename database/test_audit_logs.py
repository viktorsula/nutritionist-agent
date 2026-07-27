"""
Тесты database/queries.py::get_audit_logs / get_clients_by_ids (P2-8).

audit_logs пишется давно (write_audit_log из множества мест), но пути чтения не
было. Проверяем фильтры, курсорную пагинацию (`before`) и подстановку имён клиентов.
"""

from unittest.mock import patch

from database import queries


def test_get_audit_logs_no_filters_only_orders_and_limits():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[{"id": "1"}]):
        result = queries.get_audit_logs()

    table = mock_client.return_value.table
    table.assert_called_once_with("audit_logs")
    select = table.return_value.select
    select.assert_called_once_with("*")
    select.return_value.eq.assert_not_called()
    select.return_value.lt.assert_not_called()
    order_call = select.return_value.order
    order_call.assert_called_once_with("timestamp", desc=True)
    order_call.return_value.limit.assert_called_once_with(50)
    assert result == [{"id": "1"}]


def test_get_audit_logs_applies_entity_actor_action_filters():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_audit_logs(entity_type="client", actor_type="nutritionist", action="change_status")

    select = mock_client.return_value.table.return_value.select
    entity_eq = select.return_value.eq
    entity_eq.assert_called_once_with("entity_type", "client")
    actor_eq = entity_eq.return_value.eq
    actor_eq.assert_called_once_with("actor_type", "nutritionist")
    action_eq = actor_eq.return_value.eq
    action_eq.assert_called_once_with("action", "change_status")


def test_get_audit_logs_before_cursor_uses_lt_on_timestamp():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_audit_logs(before="2026-07-27T10:00:00", limit=10)

    select = mock_client.return_value.table.return_value.select
    select.return_value.lt.assert_called_once_with("timestamp", "2026-07-27T10:00:00")
    order_call = select.return_value.lt.return_value.order
    order_call.return_value.limit.assert_called_once_with(10)


def test_get_audit_logs_empty_result_returns_empty_list():
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=None):
        assert queries.get_audit_logs() == []


def test_get_clients_by_ids_empty_short_circuits():
    with patch("database.queries._service_client") as mock_client:
        result = queries.get_clients_by_ids([])
    assert result == []
    mock_client.assert_not_called()


def test_get_clients_by_ids_filters_by_id_list():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[{"id": "c1", "name": "Анна"}]):
        result = queries.get_clients_by_ids(["c1", "c2"])

    table = mock_client.return_value.table
    table.assert_called_once_with("clients")
    in_call = table.return_value.select.return_value.in_
    in_call.assert_called_once_with("id", ["c1", "c2"])
    assert result == [{"id": "c1", "name": "Анна"}]
