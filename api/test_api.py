"""
Тесты FastAPI-приложения (api/main.py).

Аутентификация подменяется через app.dependency_overrides (без реального Supabase),
вызовы агента — через unittest.mock (без LLM). Проверяем гейты ролей и проброс
client_id/nutritionist_id ИЗ токена (не из тела запроса).

Запуск: python -m unittest api.test_api
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from api.auth import get_current_user

CLIENT_USER = {"role": "client", "user_id": "u-1", "client_id": "c-1", "auth_id": "a-1"}
NUTRI_USER = {"role": "nutritionist", "user_id": "u-2", "client_id": None, "auth_id": "a-2"}


class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    # --- /health ---
    def test_health(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    # --- /me ---
    def test_me_requires_auth(self):
        r = self.client.get("/me")  # без Authorization
        self.assertEqual(r.status_code, 401)

    def test_me_returns_user(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.get("/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "client")
        self.assertEqual(r.json()["client_id"], "c-1")

    # --- /chat (роль client) ---
    def test_chat_rejects_nutritionist(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/chat", json={"message": "привет"})
        self.assertEqual(r.status_code, 403)

    def test_chat_client_ok_uses_token_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch(
            "agents.router.route_to_client",
            return_value={"success": True, "role": "client", "message": "ответ"},
        ) as m:
            # client_id в теле — провокация: должен игнорироваться, берётся из токена
            r = self.client.post("/chat", json={"message": "привет", "client_id": "HACK"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["message"], "ответ")
        self.assertEqual(m.call_args.kwargs["client_id"], "c-1")

    def test_chat_missing_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: {
            "role": "client", "user_id": "u", "client_id": None
        }
        r = self.client.post("/chat", json={"message": "привет"})
        self.assertEqual(r.status_code, 400)

    def test_chat_empty_message_validation(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/chat", json={"message": ""})
        self.assertEqual(r.status_code, 422)

    # --- /questionnaire-summary (роль client, миграция 017) ---
    def test_questionnaire_summary_rejects_nutritionist(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/questionnaire-summary")
        self.assertEqual(r.status_code, 403)

    def test_questionnaire_summary_missing_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: {
            "role": "client", "user_id": "u", "client_id": None
        }
        r = self.client.post("/questionnaire-summary")
        self.assertEqual(r.status_code, 400)

    def test_questionnaire_summary_ok_saves_and_notifies(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_client_profile", return_value={"goals": "снижение веса"}), \
             patch("agents.client.questionnaire_summary.build_questionnaire_summary",
                   return_value="Катя хочет снизить вес.") as build_mock, \
             patch("database.queries.set_questionnaire_summary") as set_mock, \
             patch("utils.notify.nutritionist_chat_id", return_value="12345"), \
             patch("database.queries.log_client_event") as log_mock:
            r = self.client.post("/questionnaire-summary")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["summary"], "Катя хочет снизить вес.")
        build_mock.assert_called_once_with({"goals": "снижение веса"})
        set_mock.assert_called_once_with("c-1", "Катя хочет снизить вес.")
        log_mock.assert_called_once()
        self.assertEqual(log_mock.call_args.kwargs["event_type"], "questionnaire_updated")
        self.assertEqual(log_mock.call_args.kwargs["severity"], "medium")

    def test_questionnaire_summary_no_nutritionist_telegram_skips_event(self):
        # Нутрициолог не привязал Telegram — некому слать, событие не создаём.
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_client_profile", return_value={}), \
             patch("agents.client.questionnaire_summary.build_questionnaire_summary",
                   return_value=None), \
             patch("utils.notify.nutritionist_chat_id", return_value=None), \
             patch("database.queries.log_client_event") as log_mock:
            r = self.client.post("/questionnaire-summary")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["summary"])
        log_mock.assert_not_called()

    def test_questionnaire_summary_llm_failure_still_notifies(self):
        # Саммари не собралось (сбой LLM) — уведомление всё равно уходит, без текста сводки.
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_client_profile", return_value={}), \
             patch("agents.client.questionnaire_summary.build_questionnaire_summary",
                   return_value=None), \
             patch("database.queries.set_questionnaire_summary") as set_mock, \
             patch("utils.notify.nutritionist_chat_id", return_value="12345"), \
             patch("database.queries.log_client_event") as log_mock:
            r = self.client.post("/questionnaire-summary")
        self.assertEqual(r.status_code, 200)
        set_mock.assert_not_called()
        log_mock.assert_called_once()
        self.assertIn("обновил анкету", log_mock.call_args.kwargs["payload"]["message"])

    # --- /consent-text (роль client, LEGAL-1, миграция 018) ---
    def test_consent_text_rejects_nutritionist(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.get("/consent-text")
        self.assertEqual(r.status_code, 403)

    def test_consent_text_returns_default_when_no_override(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_setting", return_value=None):
            r = self.client.get("/consent-text")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["version"], "1.0")
        self.assertIn("health_data", body["ru"])
        self.assertIn("telegram_channel", body["ru"])

    def test_consent_text_returns_db_override(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        override = {"version": "2.0", "ru": {"health_data": "x", "telegram_channel": "y"}, "en": {}}
        with patch("database.queries.get_setting", return_value=override):
            r = self.client.get("/consent-text")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["version"], "2.0")

    # --- /consent (роль client, LEGAL-1/LEGAL-5, миграция 018) ---
    def test_consent_rejects_nutritionist(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/consent", json={
            "health_data": True, "telegram_channel": True,
        })
        self.assertEqual(r.status_code, 403)

    def test_consent_missing_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: {
            "role": "client", "user_id": "u", "client_id": None
        }
        r = self.client.post("/consent", json={
            "health_data": True, "telegram_channel": True,
        })
        self.assertEqual(r.status_code, 400)

    def test_consent_rejects_partial_consent(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.insert_client_consent") as insert_mock:
            r = self.client.post("/consent", json={
                "health_data": True, "telegram_channel": False,
            })
        self.assertEqual(r.status_code, 400)
        insert_mock.assert_not_called()

    def test_consent_ok_records_and_audits(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_setting", return_value=None), \
             patch("database.queries.insert_client_consent") as insert_mock, \
             patch("database.queries.write_audit_log") as audit_mock:
            r = self.client.post("/consent", json={
                "health_data": True, "telegram_channel": True,
            })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        insert_mock.assert_called_once_with(
            client_id="c-1", consent_version="1.0",
            health_data=True, telegram_channel=True,
            channel="web",
        )
        audit_mock.assert_called_once()
        self.assertEqual(audit_mock.call_args.kwargs["actor_type"], "client")
        self.assertEqual(audit_mock.call_args.kwargs["action"], "accept_consent")
        self.assertEqual(audit_mock.call_args.kwargs["entity_type"], "consent")

    # --- /nutritionist/query (роль nutritionist) ---
    def test_nutritionist_query_rejects_client(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/nutritionist/query", json={"message": "сводка"})
        self.assertEqual(r.status_code, 403)

    def test_nutritionist_query_ok_uses_token_user_id(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch(
            "agents.router.route_to_nutritionist",
            return_value={"success": True, "role": "nutritionist", "message": "отчёт"},
        ) as m:
            r = self.client.post("/nutritionist/query", json={"message": "сводка по базе"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["message"], "отчёт")
        self.assertEqual(m.call_args.kwargs["nutritionist_id"], "u-2")

    # --- /nutritionist/setting (P0-4: валидация llm_config при сохранении) ---
    def test_save_setting_rejects_client(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/nutritionist/setting", json={"key": "llm_config", "value": None})
        self.assertEqual(r.status_code, 403)

    def test_save_setting_non_llm_config_key_not_validated(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_setting", return_value=None), \
             patch("database.queries.upsert_system_setting") as upsert_mock, \
             patch("database.queries.write_audit_log"):
            r = self.client.post("/nutritionist/setting", json={"key": "trusted_sources", "value": []})
        self.assertEqual(r.status_code, 200)
        upsert_mock.assert_called_once()

    def test_save_setting_rejects_non_claude_orchestrator_provider(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.upsert_system_setting") as upsert_mock:
            r = self.client.post("/nutritionist/setting", json={
                "key": "llm_config",
                "value": {"orchestrator": {"provider": "groq", "model": "llama-3.3-70b-versatile"}},
            })
        self.assertEqual(r.status_code, 400)
        self.assertIn("orchestrator.provider", r.json()["detail"])
        upsert_mock.assert_not_called()

    def test_save_setting_accepts_claude_orchestrator_provider(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_setting", return_value=None), \
             patch("database.queries.upsert_system_setting") as upsert_mock, \
             patch("database.queries.write_audit_log"):
            r = self.client.post("/nutritionist/setting", json={
                "key": "llm_config",
                "value": {"orchestrator": {"provider": "claude", "model": "claude-sonnet-4-6"}},
            })
        self.assertEqual(r.status_code, 200)
        upsert_mock.assert_called_once()

    def test_save_setting_accepts_null_llm_config(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_setting", return_value=None), \
             patch("database.queries.upsert_system_setting") as upsert_mock, \
             patch("database.queries.write_audit_log"):
            r = self.client.post("/nutritionist/setting", json={"key": "llm_config", "value": None})
        self.assertEqual(r.status_code, 200)
        upsert_mock.assert_called_once()

    # --- /nutritionist/coverage (наблюдаемость покрытия, Ф3) ---
    def test_coverage_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.get("/nutritionist/coverage")
        self.assertEqual(r.status_code, 403)

    def test_coverage_returns_counts_and_rate(self):
        from agents.core import coverage
        coverage.reset()
        coverage.record_turn("client", "orchestrator")
        coverage.record_turn("client", "orchestrator")
        coverage.record_turn("client", "graph_fallback")
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.get("/nutritionist/coverage")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["counts"]["client:orchestrator"], 2)
        self.assertEqual(body["fallbacks"]["client"], 1)
        self.assertAlmostEqual(body["orchestrator_rate"]["client"], 0.667, places=2)
        self.assertIsNone(body["orchestrator_rate"]["nutritionist"])  # ходов нет

    # --- /nutrition/daily (графики питания, C1) ---
    def test_nutrition_daily_client_uses_token_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        with patch("database.queries.get_nutrition_daily", return_value=[{"date": "2026-07-01"}]) as g, \
             patch("database.queries.get_active_nutrition_plan",
                   return_value={"plan_json": {"target_calories": 1800, "water_ml_target": 2000}}):
            r = self.client.get("/nutrition/daily?client_id=HACK&days=7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(g.call_args.args[0], "c-1")  # из токена, не из query (HACK игнор)
        body = r.json()
        self.assertEqual(body["targets"], {"kcal": 1800, "water_ml": 2000})
        self.assertEqual(body["series"], [{"date": "2026-07-01"}])

    def test_nutrition_daily_nutritionist_requires_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.get("/nutrition/daily")
        self.assertEqual(r.status_code, 400)

    def test_nutrition_daily_nutritionist_ok_with_client_id(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_nutrition_daily", return_value=[]) as g, \
             patch("database.queries.get_active_nutrition_plan", return_value={}):
            r = self.client.get("/nutrition/daily?client_id=c-9")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(g.call_args.args[0], "c-9")

    # --- /clients/{id}/status (редактор статусов, PR A) ---
    def test_client_status_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/clients/c-1/status", json={"payment_status": "active"})
        self.assertEqual(r.status_code, 403)

    def test_client_status_updates_and_audits(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_client_by_id",
                   return_value={"payment_status": "inactive", "paid_until": None}), \
             patch("database.queries.update_client_status") as upd, \
             patch("database.queries.write_audit_log") as audit:
            r = self.client.post("/clients/c-9/status",
                                 json={"payment_status": "active", "paid_until": "2026-08-01"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(upd.call_args.kwargs["payment_status"], "active")
        self.assertEqual(upd.call_args.kwargs["paid_until"], "2026-08-01")
        audit.assert_called_once()
        self.assertEqual(audit.call_args.kwargs["action"], "change_status")

    def test_client_status_empty_fields_400(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_client_by_id", return_value={"payment_status": "active"}):
            r = self.client.post("/clients/c-9/status", json={})
        self.assertEqual(r.status_code, 400)

    # --- /clients/{id}/reminders (напоминания, Фаза 1) ---
    def test_reminders_list_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.get("/clients/c-1/reminders")
        self.assertEqual(r.status_code, 403)

    def test_reminders_create_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/clients/c-1/reminders", json={"title": "x", "remind_at": "07:00"})
        self.assertEqual(r.status_code, 403)

    def test_reminders_create_ok_and_audits(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.create_reminder", return_value={"id": "rem-1"}) as cr, \
             patch("database.queries.write_audit_log") as audit:
            r = self.client.post("/clients/c-9/reminders",
                                 json={"title": "Прислать вес", "remind_at": "07:00", "recurrence": "daily"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(cr.call_args.kwargs["title"], "Прислать вес")
        self.assertEqual(audit.call_args.kwargs["action"], "create_reminder")
        self.assertEqual(audit.call_args.kwargs["entity_type"], "reminder")

    def test_reminders_create_passes_expected_response(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.create_reminder", return_value={"id": "rem-2"}) as cr, \
             patch("database.queries.write_audit_log"):
            r = self.client.post("/clients/c-9/reminders",
                                 json={"title": "Прислать вес", "remind_at": "07:00",
                                       "requires_response": True, "expected_response": "weight"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(cr.call_args.kwargs["requires_response"], True)
        self.assertEqual(cr.call_args.kwargs["expected_response"], "weight")

    def test_reminders_create_weekly_without_weekday_400(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/clients/c-9/reminders",
                             json={"title": "Замеры", "remind_at": "18:00", "recurrence": "weekly"})
        self.assertEqual(r.status_code, 400)

    def test_reminders_create_empty_title_400(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/clients/c-9/reminders", json={"title": "  ", "remind_at": "07:00"})
        self.assertEqual(r.status_code, 400)

    def test_reminders_patch_empty_400(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.patch("/clients/c-9/reminders/rem-1", json={})
        self.assertEqual(r.status_code, 400)

    def test_reminders_delete_ok_and_audits(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.delete_reminder") as dr, \
             patch("database.queries.write_audit_log") as audit:
            r = self.client.delete("/clients/c-9/reminders/rem-1")
        self.assertEqual(r.status_code, 200)
        dr.assert_called_once_with("rem-1")
        self.assertEqual(audit.call_args.kwargs["action"], "delete_reminder")

    # --- /clients/{id}/controlled-metrics (каталог показателей, Слайс 2C) ---
    def test_controlled_metrics_list_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.get("/clients/c-1/controlled-metrics")
        self.assertEqual(r.status_code, 403)

    def test_controlled_metrics_set_normalizes_category_and_audits(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.set_controlled_metrics") as setm, \
             patch("database.queries.write_audit_log") as audit:
            r = self.client.put("/clients/c-9/controlled-metrics", json={"metrics": [
                {"key": "waist", "label_ru": "Талия", "unit": "см"},
                {"key": "пульс", "label_ru": "Пульс", "unit": "уд/мин"},
                {"key": "", "label_ru": "мусор"},  # без ключа — отбрасывается
            ]})
        self.assertEqual(r.status_code, 200)
        saved = setm.call_args.args[1]
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["category"], "physical")  # waist
        self.assertEqual(saved[1]["category"], "custom")    # пульс
        self.assertEqual(audit.call_args.kwargs["action"], "set_controlled_metrics")

    # --- /clients/{id}/audit-findings (NEW-1, проактивный аудит клиента) ---
    def test_audit_findings_list_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.get("/clients/c-1/audit-findings")
        self.assertEqual(r.status_code, 403)

    def test_audit_findings_list_defaults_to_open(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_audit_findings", return_value=[{"id": "f1"}]) as m:
            r = self.client.get("/clients/c-1/audit-findings")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["findings"], [{"id": "f1"}])
        m.assert_called_once_with("c-1", status="open")

    def test_audit_findings_list_all_with_empty_status(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_audit_findings", return_value=[]) as m:
            r = self.client.get("/clients/c-1/audit-findings?status_filter=")
        self.assertEqual(r.status_code, 200)
        m.assert_called_once_with("c-1", status="")

    def test_audit_findings_dismiss_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/clients/c-1/audit-findings/f-1/dismiss")
        self.assertEqual(r.status_code, 403)

    def test_audit_findings_dismiss_ok(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.dismiss_audit_finding") as m:
            r = self.client.post("/clients/c-1/audit-findings/f-1/dismiss")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["ok"])
        m.assert_called_once_with("f-1", "u-2")

    # --- /clients (приглашение клиента, роль nutritionist) ---
    def test_create_client_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/clients", json={"email": "a@b.com", "name": "Иван"})
        self.assertEqual(r.status_code, 403)

    def test_create_client_invalid_email(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        r = self.client.post("/clients", json={"email": "bademail", "name": "Иван", "paid": False})
        self.assertEqual(r.status_code, 400)

    def test_create_client_ok(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        created = {"auth_id": "au-9", "user_id": "u-9", "client_id": "c-9", "email": "a@b.com"}
        with patch("database.auth.invite_client_account", return_value=created) as m:
            r = self.client.post("/clients", json={"email": "a@b.com", "name": "Иван", "paid": False})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["client_id"], "c-9")
        self.assertEqual(m.call_args.kwargs["actor_user_id"], "u-2")

    # --- /clients/{id}/reset-password (роль nutritionist) ---
    def test_reset_password_rejects_client_role(self):
        app.dependency_overrides[get_current_user] = lambda: CLIENT_USER
        r = self.client.post("/clients/c-1/reset-password")
        self.assertEqual(r.status_code, 403)

    def test_reset_password_client_not_found(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_client_by_id", return_value=None):
            r = self.client.post("/clients/nope/reset-password")
        self.assertEqual(r.status_code, 404)

    def test_reset_password_no_auth_account(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        with patch("database.queries.get_client_by_id", return_value={"id": "c-1", "user_id": "u-1"}), \
             patch("database.queries.get_user_auth_id", return_value=None):
            r = self.client.post("/clients/c-1/reset-password")
        self.assertEqual(r.status_code, 409)

    def test_reset_password_ok_sets_and_emails(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        client_row = {"id": "c-1", "user_id": "u-1", "name": "Катя", "email": "k@mail.ru"}
        with patch("database.queries.get_client_by_id", return_value=client_row), \
             patch("database.queries.get_user_auth_id", return_value="au-1"), \
             patch("database.auth.set_user_password") as set_pw, \
             patch("utils.mailer.send_email", return_value={"sent": True, "reason": ""}) as send, \
             patch("database.queries.write_audit_log") as audit:
            r = self.client.post("/clients/c-1/reset-password")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["password"])                 # пароль возвращён для показа
        self.assertTrue(body["email_sent"])
        # пароль реально передан в admin-сеттер и в письмо, но НЕ в аудит
        self.assertEqual(set_pw.call_args.args[0], "au-1")
        self.assertEqual(set_pw.call_args.args[1], body["password"])
        self.assertIn(body["password"], send.call_args.kwargs["body"])
        self.assertEqual(audit.call_args.kwargs["action"], "reset_client_password")
        self.assertNotIn("password", audit.call_args.kwargs.get("new_value", {}))

    def test_reset_password_admin_failure_502(self):
        app.dependency_overrides[get_current_user] = lambda: NUTRI_USER
        client_row = {"id": "c-1", "user_id": "u-1", "name": "Катя", "email": "k@mail.ru"}
        with patch("database.queries.get_client_by_id", return_value=client_row), \
             patch("database.queries.get_user_auth_id", return_value="au-1"), \
             patch("database.auth.set_user_password", side_effect=RuntimeError("GoTrue admin 500: boom")):
            r = self.client.post("/clients/c-1/reset-password")
        self.assertEqual(r.status_code, 502)


class TestConfigureLogging(unittest.TestCase):
    """Логирование веб-процесса: наши модули на INFO, COVERAGE эмитится, 3rd-party тихо."""

    import logging as _logging

    def _names(self):
        return ("agents", "api", "database", "utils", "business_rules", "monitoring")

    def test_our_namespaces_at_info_by_default(self):
        import logging
        import os
        from api.main import _configure_logging

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            _configure_logging()
        for name in self._names():
            self.assertEqual(logging.getLogger(name).level, logging.INFO, name)

    def test_coverage_logger_emits_info(self):
        import logging
        import os
        from api.main import _configure_logging

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            _configure_logging()
        # COVERAGE пишет agents.core.coverage.logger.info — должен пройти по уровню
        self.assertTrue(
            logging.getLogger("agents.core.coverage").isEnabledFor(logging.INFO)
        )
        # сторонние (например, httpx) наследуют корень WARNING — INFO не проходит
        self.assertFalse(logging.getLogger("httpx").isEnabledFor(logging.INFO))

    def test_log_level_override(self):
        import logging
        import os
        from api.main import _configure_logging

        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}, clear=False):
            _configure_logging()
        self.assertEqual(logging.getLogger("agents").level, logging.WARNING)
        # вернём INFO, чтобы не влиять на другие тесты
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LOG_LEVEL", None)
            _configure_logging()


class TestWebhookSecret(unittest.TestCase):
    """P2-12: проверка секрета вебхука обязательна (fail closed)."""

    def test_rejects_when_secret_not_configured(self):
        # Раньше здесь был `return True` — маршрут принимал POST от кого угодно.
        import os
        from api.telegram_webhook import webhook_secret_ok

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            self.assertFalse(webhook_secret_ok("что-угодно"))
            self.assertFalse(webhook_secret_ok(None))

    def test_accepts_matching_secret(self):
        import os
        from api.telegram_webhook import webhook_secret_ok

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "s3cret"}, clear=False):
            self.assertTrue(webhook_secret_ok("s3cret"))

    def test_rejects_wrong_or_missing_header(self):
        import os
        from api.telegram_webhook import webhook_secret_ok

        with patch.dict(os.environ, {"TELEGRAM_WEBHOOK_SECRET": "s3cret"}, clear=False):
            self.assertFalse(webhook_secret_ok("другой"))
            self.assertFalse(webhook_secret_ok(None))
            self.assertFalse(webhook_secret_ok(""))
            # префикс верного секрета не должен проходить
            self.assertFalse(webhook_secret_ok("s3c"))

    def test_endpoint_returns_403_without_secret_configured(self):
        import os

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
            client = TestClient(app)
            resp = client.post("/telegram/webhook", json={"update_id": 1})
        self.assertEqual(resp.status_code, 403)


if __name__ == "__main__":
    unittest.main()
