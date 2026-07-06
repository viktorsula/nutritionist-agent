"""
get_outstanding_occurrences: незакрытое «со вчера» для вплетения в следующее сообщение.
Приёмы пищи (breakfast/lunch/dinner) исключаются — они one-shot в пределах дня
(пропуск → алерт нутрициологу), на завтра не переносятся.
"""

from unittest.mock import patch

from database import queries


def _occ(expected, status="expired", requires=True, active=True):
    return {
        "id": f"o-{expected}",
        "status": status,
        "reminders": {
            "title": expected,
            "expected_response": expected,
            "requires_response": requires,
            "active": active,
        },
    }


def test_outstanding_excludes_meals():
    rows = [_occ("water"), _occ("weight"), _occ("breakfast"), _occ("lunch"), _occ("dinner")]
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=rows):
        out = queries.get_outstanding_occurrences("cid", "2026-07-05")
    keys = {o["reminders"]["expected_response"] for o in out}
    assert keys == {"water", "weight"}  # все три приёма пищи исключены


def test_outstanding_keeps_only_requires_response_and_active():
    rows = [
        _occ("water", requires=False),  # ответ не ждём
        _occ("weight", active=False),   # напоминание выключено
        _occ("sleep"),                  # валидное
    ]
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=rows):
        out = queries.get_outstanding_occurrences("cid", "2026-07-05")
    assert [o["reminders"]["expected_response"] for o in out] == ["sleep"]
