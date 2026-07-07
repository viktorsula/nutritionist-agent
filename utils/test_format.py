"""Тесты постобработки представления (utils/format.py)."""

import unittest

from utils.format import tables_to_text


class TestTablesToText(unittest.TestCase):
    def test_no_table_unchanged(self):
        txt = "Привет! За неделю жалоб не было. Как ты сейчас?"
        self.assertEqual(tables_to_text(txt), txt)

    def test_empty_and_none(self):
        self.assertEqual(tables_to_text(""), "")
        self.assertEqual(tables_to_text(None), None)

    def test_stray_pipe_not_a_table(self):
        # одиночный '|' в прозе не должен триггерить (нет строки-разделителя)
        txt = "Можно кашу | или омлет на выбор."
        self.assertEqual(tables_to_text(txt), txt)

    def test_converts_table_rows_to_list(self):
        md = (
            "Вот завтраки:\n"
            "| Дата | Что ела | Ккал |\n"
            "|---|---|---|\n"
            "| 30 июня | Курица с овощами | ~400 ккал |\n"
            "| 1 июля | Паста гратен | ~1055 ккал |\n"
            "Если ещё что-то — расскажи!"
        )
        out = tables_to_text(md)
        self.assertNotIn("|", out)
        self.assertNotIn("---", out)
        self.assertIn("- 30 июня — Курица с овощами — ~400 ккал", out)
        self.assertIn("- 1 июля — Паста гратен — ~1055 ккал", out)
        # окружающий текст сохранён
        self.assertIn("Вот завтраки:", out)
        self.assertIn("Если ещё что-то — расскажи!", out)

    def test_table_without_outer_pipes(self):
        md = "Дата | Статус\n--- | ---\n2 июля | Плохо\n7 июля | Плохо"
        out = tables_to_text(md)
        self.assertIn("- 2 июля — Плохо", out)
        self.assertIn("- 7 июля — Плохо", out)
        self.assertNotIn("|", out)

    def test_multiple_tables(self):
        md = (
            "| A | B |\n|---|---|\n| 1 | 2 |\n"
            "текст между\n"
            "| C | D |\n|---|---|\n| 3 | 4 |"
        )
        out = tables_to_text(md)
        self.assertIn("- 1 — 2", out)
        self.assertIn("- 3 — 4", out)
        self.assertIn("текст между", out)
        self.assertNotIn("|", out)

    def test_malformed_separator_only_no_crash(self):
        md = "| Дата | Ккал |\n|---|---|\n"
        out = tables_to_text(md)  # нет рядов данных — просто не падаем
        self.assertNotIn("|", out)


if __name__ == "__main__":
    unittest.main()
