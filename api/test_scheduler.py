"""
Тесты планировщика уведомлений (api/scheduler.py) — чистая логика без сети.
"""

import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytz

from api import scheduler as S
from utils import notify


class TestIsDue(unittest.TestCase):
    def _utc(self, h, m):
        return datetime(2026, 6, 24, h, m, tzinfo=pytz.UTC)

    def test_due_in_client_timezone(self):
        # 08:00 в Asia/Dubai (UTC+4) = 04:00 UTC
        due, stamp = S._is_due("08:00:00", "Asia/Dubai", now_utc=self._utc(4, 0))
        self.assertTrue(due)
        self.assertEqual(stamp, "2026-06-24 08:00")

    def test_not_due_other_minute(self):
        due, _ = S._is_due("08:00:00", "Asia/Dubai", now_utc=self._utc(4, 1))
        self.assertFalse(due)

    def test_utc_zone(self):
        due, _ = S._is_due("09:30:00", "UTC", now_utc=self._utc(9, 30))
        self.assertTrue(due)

    def test_bad_timezone_falls_back_to_utc(self):
        due, _ = S._is_due("09:30:00", "Mars/Phobos", now_utc=self._utc(9, 30))
        self.assertTrue(due)

    def test_empty_scheduled_time(self):
        due, stamp = S._is_due(None, "UTC", now_utc=self._utc(9, 30))
        self.assertFalse(due)
        self.assertEqual(stamp, "")

    def test_malformed_time(self):
        due, _ = S._is_due("notatime", "UTC", now_utc=self._utc(9, 30))
        self.assertFalse(due)


class TestMessageFor(unittest.TestCase):
    def test_known_types(self):
        self.assertIn("утро", S._message_for("morning").lower())
        self.assertIn("вечер", S._message_for("evening").lower())

    def test_unknown_type_defaults_to_reminder(self):
        self.assertEqual(S._message_for("whatever"), S.NOTIFICATION_TEMPLATES["reminder"])
        self.assertEqual(S._message_for(None), S.NOTIFICATION_TEMPLATES["reminder"])


class TestFormatAlert(unittest.TestCase):
    def test_format_includes_client_severity_detail(self):
        ev = {
            "event_type": "bad_wellbeing",
            "severity": "medium",
            "payload_json": {"reason": "болит голова"},
            "clients": {"name": "Марина"},
        }
        text = notify.format_alert(ev)
        self.assertIn("Плохое самочувствие", text)
        self.assertIn("Марина", text)
        self.assertIn("болит голова", text)

    def test_format_unknown_type_and_no_detail(self):
        ev = {"event_type": "weird", "severity": "high", "payload_json": {}, "clients": {}}
        text = notify.format_alert(ev)
        self.assertIn("weird", text)
        self.assertIn("high", text)

    def test_chat_id_from_env(self):
        with patch.dict(os.environ, {"NUTRITIONIST_TELEGRAM_ID": "  555  "}):
            self.assertEqual(notify.nutritionist_chat_id(), "555")
        with patch.dict(os.environ, {"NUTRITIONIST_TELEGRAM_ID": ""}, clear=False):
            self.assertIsNone(notify.nutritionist_chat_id())


class TestRunNutritionistAlerts(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        S._alert_guard.clear()

    async def _run(self, events, *, configured=True, chat_id="555"):
        bot = AsyncMock()
        env = {"NUTRITIONIST_TELEGRAM_ID": chat_id} if chat_id is not None else {}
        with patch("api.telegram_webhook.is_configured", return_value=configured), \
             patch("api.telegram_webhook.get_bot", return_value=bot), \
             patch("database.queries.get_recent_alert_events", return_value=events), \
             patch.dict(os.environ, env, clear=False):
            if chat_id is None:
                os.environ.pop("NUTRITIONIST_TELEGRAM_ID", None)
            await S.run_nutritionist_alerts()
        return bot

    async def test_sends_each_event_once(self):
        events = [
            {"id": "e1", "event_type": "bad_wellbeing", "severity": "medium",
             "payload_json": {"reason": "тошнит"}, "clients": {"name": "Иван"}},
            {"id": "e2", "event_type": "weight_increase", "severity": "high",
             "payload_json": {}, "clients": {"name": "Ольга"}},
        ]
        bot = await self._run(events)
        self.assertEqual(bot.send_message.call_count, 2)
        # повторный проход тех же событий — дедуп, ничего не шлём
        bot2 = await self._run(events)
        self.assertEqual(bot2.send_message.call_count, 0)

    async def test_skips_when_no_chat_id(self):
        events = [{"id": "e1", "event_type": "bad_wellbeing", "severity": "medium",
                   "payload_json": {}, "clients": {}}]
        bot = await self._run(events, chat_id=None)
        bot.send_message.assert_not_called()

    async def test_skips_when_bot_not_configured(self):
        events = [{"id": "e1", "event_type": "bad_wellbeing", "severity": "medium",
                   "payload_json": {}, "clients": {}}]
        bot = await self._run(events, configured=False)
        bot.send_message.assert_not_called()


class TestReminderDueToday(unittest.TestCase):
    def _local(self, y, mo, d, h=8, mi=0):
        return pytz.timezone("Asia/Dubai").localize(datetime(y, mo, d, h, mi))

    def test_daily_always_due(self):
        self.assertTrue(S._reminder_due_today({"recurrence": "daily"}, self._local(2026, 6, 24)))

    def test_weekly_matches_weekday(self):
        now = self._local(2026, 6, 24)  # среда
        self.assertTrue(S._reminder_due_today({"recurrence": "weekly", "weekday": now.weekday()}, now))
        self.assertFalse(S._reminder_due_today({"recurrence": "weekly", "weekday": (now.weekday() + 1) % 7}, now))

    def test_once_matches_date(self):
        now = self._local(2026, 6, 24)
        self.assertTrue(S._reminder_due_today({"recurrence": "once", "remind_date": "2026-06-24"}, now))
        self.assertFalse(S._reminder_due_today({"recurrence": "once", "remind_date": "2026-06-25"}, now))
        self.assertFalse(S._reminder_due_today({"recurrence": "once", "remind_date": None}, now))


class TestFallbackReminderText(unittest.TestCase):
    def test_single(self):
        self.assertEqual(S._fallback_reminder_text(["Выпить воды"]), "🔔 Напоминание: Выпить воды")

    def test_multiple_lists_all(self):
        text = S._fallback_reminder_text(["Выпить воды", "Прислать вес"])
        self.assertIn("• Выпить воды", text)
        self.assertIn("• Прислать вес", text)


class TestComposeReminderMessage(unittest.TestCase):
    def test_uses_llm_when_available(self):
        with patch("utils.llm.call_llm", return_value={"content": "Доброе утро! Не забудьте про воду 💧"}), \
             patch("prompts.load_prompt", return_value="sys"):
            self.assertEqual(S.compose_reminder_message(["Выпить воды"]), "Доброе утро! Не забудьте про воду 💧")

    def test_falls_back_on_llm_error(self):
        with patch("utils.llm.call_llm", side_effect=RuntimeError("429")), \
             patch("prompts.load_prompt", return_value="sys"):
            self.assertEqual(S.compose_reminder_message(["Выпить воды"]), "🔔 Напоминание: Выпить воды")


class TestRunReminders(unittest.IsolatedAsyncioTestCase):
    def _reminder(self, rid, title, at="08:00:00", rec="daily", **extra):
        r = {"id": rid, "client_id": "c1", "title": title, "remind_at": at, "recurrence": rec,
             "weekday": None, "remind_date": None, "clients": {"telegram_id": 777, "timezone": "Asia/Dubai"}}
        r.update(extra)
        return r

    async def _run(self, reminders, *, exists=False, utc=(4, 0), configured=True):
        bot = AsyncMock()
        recorded = []
        # 04:00 UTC = 08:00 Asia/Dubai
        fake_now = datetime(2026, 6, 24, utc[0], utc[1])
        with patch("api.scheduler.datetime") as mock_dt, \
             patch("api.telegram_webhook.is_configured", return_value=configured), \
             patch("api.telegram_webhook.get_bot", return_value=bot), \
             patch("database.queries.get_active_reminders", return_value=reminders), \
             patch("database.queries.occurrence_exists", return_value=exists), \
             patch("database.queries.record_occurrence", side_effect=lambda *a, **k: recorded.append(a)), \
             patch("api.scheduler.compose_reminder_message", side_effect=lambda titles: " | ".join(titles)):
            mock_dt.utcnow.return_value = fake_now
            await S.run_reminders()
        return bot, recorded

    async def test_batches_same_time_into_one_message(self):
        reminders = [self._reminder("r1", "Выпить воды"), self._reminder("r2", "Прислать вес")]
        bot, recorded = await self._run(reminders)
        self.assertEqual(bot.send_message.call_count, 1)  # один пакет
        text = bot.send_message.call_args.kwargs["text"]
        self.assertIn("Выпить воды", text)
        self.assertIn("Прислать вес", text)
        self.assertEqual(len(recorded), 2)  # оба срабатывания зафиксированы

    async def test_dedup_skips_already_sent(self):
        bot, _ = await self._run([self._reminder("r1", "Выпить воды")], exists=True)
        bot.send_message.assert_not_called()

    async def test_wrong_minute_no_send(self):
        bot, _ = await self._run([self._reminder("r1", "Выпить воды")], utc=(4, 5))  # 08:05, не 08:00
        bot.send_message.assert_not_called()

    async def test_weekly_wrong_day_no_send(self):
        # 2026-06-24 среда (weekday 2); ставим понедельник (0) → не шлём
        bot, _ = await self._run([self._reminder("r1", "Замеры", rec="weekly", weekday=0)])
        bot.send_message.assert_not_called()

    async def test_skips_client_without_telegram(self):
        r = self._reminder("r1", "Выпить воды")
        r["clients"] = {"telegram_id": None, "timezone": "Asia/Dubai"}
        bot, _ = await self._run([r])
        bot.send_message.assert_not_called()


class TestCadence(unittest.TestCase):
    def test_cadence_keys(self):
        self.assertEqual(S._cadence_key("weight"), "weight")
        self.assertEqual(S._cadence_key("waist"), "measurement")
        self.assertEqual(S._cadence_key("sleep"), "sleep")
        self.assertEqual(S._cadence_key("labs"), "labs")
        self.assertEqual(S._cadence_key("text"), "text")
        self.assertEqual(S._cadence_key(None), "text")
        self.assertEqual(S._cadence_key("пульс"), "default")

    def test_resolve_cadence_uses_code_defaults(self):
        with patch("database.queries.get_setting", return_value=None):
            self.assertEqual(S.resolve_cadence("weight")["give_up_hours"], 14)
            self.assertEqual(S.resolve_cadence("labs")["give_up_hours"], 168)

    def test_resolve_cadence_db_override_merges(self):
        with patch("database.queries.get_setting", return_value={"weight": {"give_up_hours": 6}}):
            prof = S.resolve_cadence("weight")
            self.assertEqual(prof["give_up_hours"], 6)      # переопределено
            self.assertEqual(prof["followup_hours"], 3)     # дефолт сохранён


class TestDetectResponse(unittest.TestCase):
    def test_routes_by_type(self):
        with patch("database.queries.has_measurement_since", return_value=True) as hm:
            self.assertTrue(S._detect_response("c", "weight", "2026-06-24T07:00:00"))
            self.assertEqual(hm.call_args.args[1], "weight")
        with patch("database.queries.has_client_metric_since", return_value=True) as hcm:
            self.assertTrue(S._detect_response("c", "sleep", "2026-06-24T07:00:00"))
            self.assertEqual(hcm.call_args.args[1], "sleep")
        with patch("database.queries.has_lab_result_since", return_value=False):
            self.assertFalse(S._detect_response("c", "labs", "2026-06-24T07:00:00"))
        with patch("database.queries.has_client_message_since", return_value=True):
            self.assertTrue(S._detect_response("c", "text", "2026-06-24T07:00:00"))
            self.assertTrue(S._detect_response("c", None, "2026-06-24T07:00:00"))
        with patch("database.queries.has_event_since", return_value=True) as he:
            self.assertTrue(S._detect_response("c", "water", "2026-06-24T07:00:00"))
            self.assertEqual(he.call_args.args[1], "water_logged")
        with patch("database.queries.has_meal_event_since", return_value=True) as hme:
            self.assertTrue(S._detect_response("c", "lunch", "2026-06-24T07:00:00"))
            self.assertEqual(hme.call_args.args[1], "lunch")


class TestItemCadence(unittest.TestCase):
    def test_per_item_overrides_profile(self):
        with patch("database.queries.get_setting", return_value=None):
            prof = S._item_cadence({"expected_response": "weight",
                                    "followup_after_hours": 5, "max_followups": 3})
            self.assertEqual(prof["followup_hours"], 5)   # переопределено
            self.assertEqual(prof["max_followups"], 3)

    def test_meal_and_water_keys(self):
        self.assertEqual(S._cadence_key("breakfast"), "meals")
        self.assertEqual(S._cadence_key("water"), "water")
        self.assertEqual(S._cadence_key("chest"), "measurement")


class TestRunReminderFollowups(unittest.IsolatedAsyncioTestCase):
    def _occ(self, sent="2026-06-24T04:00:00", nfu=None, followups=0, expected="weight", deadline=None):
        return {
            "id": "occ1", "reminder_id": "r1", "client_id": "c1", "sent_at": sent,
            "due_date": "2026-06-24", "next_followup_at": nfu, "followups_sent": followups,
            "reminders": {"title": "Прислать вес", "expected_response": expected,
                          "requires_response": True, "active": True, "response_deadline": deadline},
            "clients": {"telegram_id": 777, "timezone": "Asia/Dubai"},
        }

    async def _run(self, occ, *, detected=False, utc=(4, 0)):
        bot = AsyncMock()
        fake_now = datetime(2026, 6, 24, utc[0], utc[1])
        with patch("api.scheduler.datetime") as mock_dt, \
             patch("api.telegram_webhook.is_configured", return_value=True), \
             patch("api.telegram_webhook.get_bot", return_value=bot), \
             patch("database.queries.get_open_occurrences", return_value=[occ]), \
             patch("api.scheduler._detect_response", return_value=detected), \
             patch("api.scheduler.compose_reminder_message", side_effect=lambda t: " | ".join(t)), \
             patch("database.queries.mark_occurrence_answered") as answered, \
             patch("database.queries.mark_occurrence_expired") as expired, \
             patch("database.queries.bump_occurrence_followup") as bumped, \
             patch("database.queries.log_client_event") as logged:
            mock_dt.utcnow.return_value = fake_now
            mock_dt.fromisoformat = datetime.fromisoformat
            mock_dt.side_effect = datetime  # реальный конструктор datetime(...) для дедлайнов
            await S.run_reminder_followups()
        return bot, answered, expired, bumped, logged

    async def test_answer_closes_occurrence(self):
        bot, answered, expired, bumped, _ = await self._run(self._occ(), detected=True)
        answered.assert_called_once()
        expired.assert_not_called()
        bumped.assert_not_called()
        bot.send_message.assert_not_called()

    async def test_give_up_expires_and_alerts(self):
        # sent 04:00 UTC, give_up 14ч (weight) → 18:00 UTC; сейчас 19:00 UTC → просрочка
        bot, answered, expired, _, logged = await self._run(self._occ(), utc=(19, 0))
        expired.assert_called_once()
        self.assertEqual(logged.call_args.kwargs["event_type"], "reminder_unanswered")
        self.assertEqual(logged.call_args.kwargs["severity"], "low")
        answered.assert_not_called()

    async def test_followup_sent_when_due(self):
        # nfu 07:00 UTC, сейчас 08:00 UTC, followups 0 < max 1 → повтор
        occ = self._occ(nfu="2026-06-24T07:00:00")
        bot, _, expired, bumped, _ = await self._run(occ, utc=(8, 0))
        bot.send_message.assert_called_once()
        bumped.assert_called_once()
        expired.assert_not_called()

    async def test_no_followup_before_time(self):
        occ = self._occ(nfu="2026-06-24T07:00:00")
        bot, _, _, bumped, _ = await self._run(occ, utc=(6, 0))  # ещё рано
        bot.send_message.assert_not_called()
        bumped.assert_not_called()

    async def test_skips_non_requires_response(self):
        occ = self._occ()
        occ["reminders"]["requires_response"] = False
        bot, answered, expired, bumped, _ = await self._run(occ)
        for m in (answered, expired, bumped):
            m.assert_not_called()

    async def test_meal_miss_alerts_medium_after_deadline(self):
        # Обед, дедлайн 17:00 Asia/Dubai (=13:00 UTC). Сейчас 14:00 UTC → просрочка → пуш-алерт.
        occ = self._occ(expected="lunch", deadline="17:00")
        bot, answered, expired, _, logged = await self._run(occ, utc=(14, 0))
        expired.assert_called_once()
        self.assertEqual(logged.call_args.kwargs["event_type"], "meal_not_reported")
        self.assertEqual(logged.call_args.kwargs["severity"], "medium")

    async def test_meal_not_expired_before_deadline(self):
        # 17:00 Dubai = 13:00 UTC; сейчас 10:00 UTC → до дедлайна, не просрочено.
        occ = self._occ(expected="lunch", deadline="17:00")
        bot, _, expired, _, logged = await self._run(occ, utc=(10, 0))
        expired.assert_not_called()
        logged.assert_not_called()


class TestNoResponseCheck(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        S._no_response_guard.clear()
        S._last_no_response_at = None

    async def test_emits_no_response_event_once_per_day(self):
        alert = {"severity": "high", "details": {"hours_since_last_message": 60}}
        with patch("database.queries.get_all_clients", return_value=[{"id": "c1"}]), \
             patch("business_rules.medical_rules._check_no_response", return_value=alert), \
             patch("database.queries.log_client_event") as logged:
            await S.run_no_response_check()
            self.assertEqual(logged.call_args.kwargs["event_type"], "no_response")
            self.assertEqual(logged.call_args.kwargs["severity"], "high")
            # второй проход в тот же день (сбрасываем тротлинг) — дедуп, событие не дублируется
            S._last_no_response_at = None
            await S.run_no_response_check()
            self.assertEqual(logged.call_count, 1)

    async def test_no_alert_when_client_active(self):
        with patch("database.queries.get_all_clients", return_value=[{"id": "c1"}]), \
             patch("business_rules.medical_rules._check_no_response", return_value=None), \
             patch("database.queries.log_client_event") as logged:
            await S.run_no_response_check()
            logged.assert_not_called()


if __name__ == "__main__":
    unittest.main()
