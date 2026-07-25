"""
Тесты database/queries.py — функции проактивного аудита клиента (NEW-1, миграция 020).
"""

from unittest.mock import MagicMock, patch

from database import queries


def test_get_clients_for_audit_empty_statuses_short_circuits():
    with patch("database.queries._service_client") as mock_client:
        result = queries.get_clients_for_audit([])
    assert result == []
    mock_client.assert_not_called()


def test_get_clients_for_audit_filters_by_status_list():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[{"id": "c1"}]):
        result = queries.get_clients_for_audit(["active"])

    table = mock_client.return_value.table
    table.assert_called_once_with("clients")
    in_call = table.return_value.select.return_value.in_
    in_call.assert_called_once_with("client_status", ["active"])
    assert result == [{"id": "c1"}]


def test_insert_audit_finding_writes_expected_fields():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._execute_one", return_value={"id": "f1"}) as exec_mock:
        result = queries.insert_audit_finding("c1", "Заголовок", "Описание", severity="low")

    insert_call = mock_client.return_value.table.return_value.insert
    insert_call.assert_called_once_with({
        "client_id": "c1",
        "title": "Заголовок",
        "description": "Описание",
        "severity": "low",
    })
    assert result == {"id": "f1"}
    exec_mock.assert_called_once()


def test_get_audit_findings_defaults_to_open_status():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_audit_findings("c1")

    table = mock_client.return_value.table
    eq_chain = table.return_value.select.return_value.eq
    eq_chain.assert_called_once_with("client_id", "c1")
    status_eq = eq_chain.return_value.eq
    status_eq.assert_called_once_with("status", "open")


def test_get_audit_findings_empty_status_skips_status_filter():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        queries.get_audit_findings("c1", status="")

    table = mock_client.return_value.table
    eq_chain = table.return_value.select.return_value.eq
    eq_chain.assert_called_once_with("client_id", "c1")
    eq_chain.return_value.eq.assert_not_called()


def test_dismiss_audit_finding_sets_status_and_dismissed_fields():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._execute_one", return_value={"id": "f1", "status": "dismissed"}) as exec_mock:
        result = queries.dismiss_audit_finding("f1", "u1")

    update_call = mock_client.return_value.table.return_value.update
    body = update_call.call_args.args[0]
    assert body["status"] == "dismissed"
    assert body["dismissed_by"] == "u1"
    assert "dismissed_at" in body
    assert result == {"id": "f1", "status": "dismissed"}
    exec_mock.assert_called_once()
