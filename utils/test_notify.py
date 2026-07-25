"""
Тесты utils/notify.py::format_alert — текст уведомления нутрициологу.
Запуск: python -m pytest utils/test_notify.py
"""

import unittest

from utils.notify import format_alert


class TestFormatAlertFoodAlerts(unittest.TestCase):
    def test_detail_from_alerts_array(self):
        """calories_logged: детали берутся из payload['alerts'][].message (не 'deviations')."""
        event = {
            "event_type": "calories_logged",
            "severity": "high",
            "clients": {"name": "Екатерина"},
            "payload_json": {
                "alerts": [
                    {"type": "food_forbidden", "severity": "high", "message": "Козий сыр — молочный продукт"},
                ],
            },
        }
        text = format_alert(event)
        self.assertIn("Козий сыр — молочный продукт", text)

    def test_multiple_alerts_joined(self):
        event = {
            "event_type": "calories_logged",
            "severity": "high",
            "clients": {"name": "Екатерина"},
            "payload_json": {
                "alerts": [
                    {"type": "food_forbidden", "message": "Молочный продукт вне плана"},
                    {"type": "allergen", "message": "Обнаружен аллерген: орехи"},
                ],
            },
        }
        text = format_alert(event)
        self.assertIn("Молочный продукт вне плана", text)
        self.assertIn("Обнаружен аллерген: орехи", text)

    def test_message_key_takes_priority_over_alerts(self):
        event = {
            "event_type": "weight_increase",
            "severity": "high",
            "clients": {"name": "Екатерина"},
            "payload_json": {"message": "Вес вырос на 1.2 кг", "alerts": [{"message": "не должно читаться"}]},
        }
        text = format_alert(event)
        self.assertIn("Вес вырос на 1.2 кг", text)
        self.assertNotIn("не должно читаться", text)

    def test_questionnaire_updated_has_readable_label(self):
        # Регрессия P1-9: новый event_type не должен светить сырым именем в Telegram.
        event = {
            "event_type": "questionnaire_updated",
            "severity": "medium",
            "clients": {"name": "Екатерина"},
            "payload_json": {"message": "Обновлена информация о медикаментах"},
        }
        text = format_alert(event)
        self.assertNotIn("questionnaire_updated", text)
        self.assertIn("Анкета обновлена", text)
        self.assertIn("Обновлена информация о медикаментах", text)

    def test_no_detail_no_alerts_line_omitted(self):
        event = {
            "event_type": "calories_logged",
            "severity": "low",
            "clients": {"name": "Екатерина"},
            "payload_json": {},
        }
        text = format_alert(event)
        self.assertNotIn("Детали:", text)

    def test_meal_not_reported_has_readable_label_and_detail(self):
        # P1-9: раньше "Алерт: meal_not_reported" без единого понятного слова.
        event = {
            "event_type": "meal_not_reported",
            "severity": "medium",
            "clients": {"name": "Екатерина"},
            "payload_json": {"title": "Обед", "expected": "lunch"},
        }
        text = format_alert(event)
        self.assertNotIn("meal_not_reported", text)
        self.assertIn("Приём пищи не отмечен", text)
        self.assertIn("Обед", text)
        self.assertIn("lunch", text)

    def test_reminder_unanswered_has_readable_label_and_detail(self):
        event = {
            "event_type": "reminder_unanswered",
            "severity": "low",
            "clients": {"name": "Екатерина"},
            "payload_json": {"title": "Контроль сна"},
        }
        text = format_alert(event)
        self.assertNotIn("reminder_unanswered", text)
        self.assertIn("Напоминание без ответа", text)
        self.assertIn("Контроль сна", text)

    def test_plan_exception_claimed_has_readable_label_and_detail(self):
        # P1-10: сигнал нутрициологу о заявлении клиента — тоже должен быть читаемым.
        event = {
            "event_type": "plan_exception_claimed",
            "severity": "low",
            "clients": {"name": "Екатерина"},
            "payload_json": {"item": "пармезан", "client_claim": "нутрициолог разрешила"},
        }
        text = format_alert(event)
        self.assertNotIn("plan_exception_claimed", text)
        self.assertIn("Клиент заявил об исключении из плана", text)
        self.assertIn("пармезан", text)
        self.assertIn("нутрициолог разрешила", text)


if __name__ == "__main__":
    unittest.main()
