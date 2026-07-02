"""
Модель доступа (PR A): 2 оси (client_status + payment_status/paid_until), access_status убран
из гейтов, авто-блок по истёкшему paid_until, paused блокирует и веб-кабинет.
"""

from unittest.mock import patch

from business_rules import access_rules as ar

PAST = "2000-01-01"
FUTURE = "2999-01-01"


# ── _payment_active ──────────────────────────────────────────────────────────
def test_payment_active_future_date():
    assert ar._payment_active({"payment_status": "active", "paid_until": FUTURE}) is True


def test_payment_active_expired_date_auto_block():
    assert ar._payment_active({"payment_status": "active", "paid_until": PAST}) is False


def test_payment_active_no_date_relies_on_status():
    assert ar._payment_active({"payment_status": "trial"}) is True
    assert ar._payment_active({"payment_status": "inactive"}) is False


# ── check_web_access ─────────────────────────────────────────────────────────
def _web(client):
    with patch("business_rules.access_rules.get_client_by_id", return_value=client):
        return ar.check_web_access("c1")


def test_web_access_ok():
    assert _web({"client_status": "active", "payment_status": "active", "paid_until": FUTURE})["allowed"] is True


def test_web_access_paused_blocks_web():
    r = _web({"client_status": "paused", "payment_status": "active", "paid_until": FUTURE})
    assert r["allowed"] is False and r["reason"] == "program_paused"


def test_web_access_expired_payment_blocks():
    r = _web({"client_status": "active", "payment_status": "active", "paid_until": PAST})
    assert r["allowed"] is False and r["reason"] == "payment_inactive"


def test_web_access_frozen_no_longer_blocks():
    # access_status убран из гейта: frozen сам по себе больше не блокирует.
    r = _web({"client_status": "active", "payment_status": "active",
              "paid_until": FUTURE, "access_status": "frozen"})
    assert r["allowed"] is True


# ── check_access (диалог с агентом) ──────────────────────────────────────────
def test_check_access_expired_payment_blocks():
    client = {"client_status": "active", "payment_status": "active", "paid_until": PAST}
    profile = {"onboarding_completed_at": "2024-01-01"}
    with patch("business_rules.access_rules.get_client_by_id", return_value=client), \
         patch("business_rules.access_rules.get_client_profile", return_value=profile):
        r = ar.check_access("c1")
    assert r["allowed"] is False and r["reason"] == "payment_inactive"


def test_check_access_active_ok_full_program():
    client = {"client_status": "active", "payment_status": "active", "paid_until": FUTURE}
    profile = {"onboarding_completed_at": "2024-01-01"}
    with patch("business_rules.access_rules.get_client_by_id", return_value=client), \
         patch("business_rules.access_rules.get_client_profile", return_value=profile):
        r = ar.check_access("c1")
    assert r["allowed"] is True and r["mode"] == "full_program"
