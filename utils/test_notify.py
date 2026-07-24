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


if __name__ == "__main__":
    unittest.main()
