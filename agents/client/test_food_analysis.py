"""
Тесты входящей точки смысловой проверки еды (P1-13, шаг 2).

Входящая точка — детерминированная: она срабатывает всегда, когда клиент записал еду,
и не зависит от того, решит ли модель что-то вызвать. Поэтому здесь проверяется, что
результат проверки корректно превращается в алерты нутрициологу и что сбой проверки не
роняет саму запись приёма пищи.
"""

from unittest.mock import patch

from agents.client.food_analysis import _semantic_food_alerts


def _result(violations=None, unclear=None, checked=True):
    return {
        "checked": checked,
        "verdicts": [],
        "violations": violations or [],
        "unclear": unclear or [],
        "blocked": bool(violations),
    }


def test_violation_becomes_high_alert():
    res = _result(violations=[{"item": "кешью", "reason": "кешью — орех"}])
    with patch("business_rules.food_check.check_food", return_value=res):
        alerts = _semantic_food_alerts("cid", ["кешью"])

    assert len(alerts) == 1
    assert alerts[0]["type"] == "food_violation"
    assert alerts[0]["severity"] == "high"
    assert "кешью" in alerts[0]["message"]


def test_unclear_becomes_low_alert_not_high():
    # «Неясно» — это вопрос нутрициологу, а не нарушение: клиента не тревожим,
    # но и молчать нельзя.
    res = _result(unclear=[{"item": "плов", "reason": "состав неизвестен"}])
    with patch("business_rules.food_check.check_food", return_value=res):
        alerts = _semantic_food_alerts("cid", ["плов"])

    assert len(alerts) == 1
    assert alerts[0]["type"] == "food_unclear"
    assert alerts[0]["severity"] == "low"


def test_violation_and_unclear_produce_separate_alerts():
    res = _result(
        violations=[{"item": "кешью", "reason": "орех"}],
        unclear=[{"item": "плов", "reason": "состав неизвестен"}],
    )
    with patch("business_rules.food_check.check_food", return_value=res):
        alerts = _semantic_food_alerts("cid", ["кешью", "плов"])

    types = sorted(a["type"] for a in alerts)
    assert types == ["food_unclear", "food_violation"]


def test_clean_result_produces_no_alerts():
    with patch("business_rules.food_check.check_food", return_value=_result()):
        assert _semantic_food_alerts("cid", ["курица"]) == []


def test_unchecked_produces_no_alerts():
    # У клиента нет ограничений — проверка не выполнялась, алертов быть не должно.
    with patch("business_rules.food_check.check_food", return_value=_result(checked=False)):
        assert _semantic_food_alerts("cid", ["курица"]) == []


def test_check_failure_does_not_break_meal_logging():
    # Сбой проверки не должен ронять запись приёма пищи — она важнее.
    with patch("business_rules.food_check.check_food", side_effect=RuntimeError("down")):
        assert _semantic_food_alerts("cid", ["курица"]) == []
