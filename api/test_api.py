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


if __name__ == "__main__":
    unittest.main()
