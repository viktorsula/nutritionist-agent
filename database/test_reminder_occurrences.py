"""
Тесты database/queries.py — кросс-джобовый дедуп напоминаний по теме (P1-7):
has_topic_message_today + last_notified_date, проставляемый record_occurrence /
bump_occurrence_followup.
"""

from unittest.mock import patch

from database import queries


def test_has_topic_message_today_false_without_topic():
    with patch("database.queries._service_client") as mock_client:
        assert queries.has_topic_message_today("c1", None, "2026-07-25") is False
        assert queries.has_topic_message_today("c1", "text", "2026-07-25") is False
        assert queries.has_topic_message_today("c1", "none", "2026-07-25") is False
    mock_client.assert_not_called()  # ранний выход — до похода в БД


def test_has_topic_message_today_false_when_no_reminders_with_topic():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data", return_value=[]):
        result = queries.has_topic_message_today("c1", "water", "2026-07-25")
    assert result is False


def test_has_topic_message_today_true_when_occurrence_notified_today():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data",
               side_effect=[[{"id": "r1"}, {"id": "r2"}], [{"id": "occ2"}]]):
        result = queries.has_topic_message_today("c1", "water", "2026-07-25")
    assert result is True

    table = mock_client.return_value.table
    reminders_call = table.return_value.select.return_value.eq.return_value.eq
    reminders_call.assert_called_once_with("expected_response", "water")

    occ_chain = table.return_value.select.return_value.in_.return_value.eq
    occ_chain.assert_called_once_with("last_notified_date", "2026-07-25")


def test_has_topic_message_today_excludes_own_occurrence():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._extract_data",
               side_effect=[[{"id": "r1"}], []]):
        result = queries.has_topic_message_today(
            "c1", "water", "2026-07-25", exclude_occurrence_id="occ1"
        )
    assert result is False

    table = mock_client.return_value.table
    neq_call = table.return_value.select.return_value.in_.return_value.eq.return_value.neq
    neq_call.assert_called_once_with("id", "occ1")


def test_record_occurrence_sets_last_notified_date_to_due_date():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._execute_one", return_value={"id": "occ1"}):
        queries.record_occurrence("r1", "c1", "2026-07-25")

    insert_call = mock_client.return_value.table.return_value.insert
    payload = insert_call.call_args.args[0]
    assert payload["last_notified_date"] == "2026-07-25"


def test_bump_occurrence_followup_updates_last_notified_date():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._execute_single", return_value={"followups_sent": 1}), \
         patch("database.queries._execute_one", return_value={"id": "occ1"}):
        queries.bump_occurrence_followup("occ1", "2026-07-26T10:00:00", notified_date="2026-07-25")

    update_call = mock_client.return_value.table.return_value.update
    payload = update_call.call_args.args[0]
    assert payload["last_notified_date"] == "2026-07-25"
    assert payload["followups_sent"] == 2


def test_bump_occurrence_followup_without_notified_date_leaves_it_unset():
    with patch("database.queries._service_client") as mock_client, \
         patch("database.queries._execute_single", return_value={"followups_sent": 0}), \
         patch("database.queries._execute_one", return_value={"id": "occ1"}):
        queries.bump_occurrence_followup("occ1", None)

    update_call = mock_client.return_value.table.return_value.update
    payload = update_call.call_args.args[0]
    assert "last_notified_date" not in payload
