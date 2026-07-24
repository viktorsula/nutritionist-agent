"""
Тесты utils/web_access.py: построение инструмента web_search + чтение
доверенных источников (system_settings.trusted_sources, P1-15/PR-D).
Запуск: python -m pytest utils/test_web_access.py
"""

import unittest
from unittest.mock import patch

from utils.web_access import build_web_search_tool, get_trusted_domains, get_trusted_sources


class TestBuildWebSearchTool(unittest.TestCase):
    def test_no_domains_by_default(self):
        tool = build_web_search_tool()
        self.assertEqual(tool["type"], "web_search_20250305")
        self.assertEqual(tool["name"], "web_search")
        self.assertNotIn("allowed_domains", tool)
        self.assertNotIn("blocked_domains", tool)

    def test_allowed_domains_set_when_given(self):
        tool = build_web_search_tool(allowed_domains=["pubmed.ncbi.nlm.nih.gov"])
        self.assertEqual(tool["allowed_domains"], ["pubmed.ncbi.nlm.nih.gov"])

    def test_allowed_domains_takes_precedence_over_blocked(self):
        tool = build_web_search_tool(allowed_domains=["a.com"], blocked_domains=["b.com"])
        self.assertIn("allowed_domains", tool)
        self.assertNotIn("blocked_domains", tool)


class TestGetTrustedSources(unittest.TestCase):
    def test_returns_empty_when_setting_missing(self):
        with patch("database.queries.get_setting", return_value=None):
            self.assertEqual(get_trusted_sources(), [])

    def test_returns_empty_when_setting_not_a_list(self):
        with patch("database.queries.get_setting", return_value="oops"):
            self.assertEqual(get_trusted_sources(), [])

    def test_filters_entries_without_url(self):
        sources = [
            {"name": "PubMed", "url": "https://pubmed.ncbi.nlm.nih.gov"},
            {"name": "No URL"},
            "not-a-dict",
        ]
        with patch("database.queries.get_setting", return_value=sources):
            result = get_trusted_sources()
        self.assertEqual(result, [{"name": "PubMed", "url": "https://pubmed.ncbi.nlm.nih.gov"}])

    def test_exception_returns_empty(self):
        with patch("database.queries.get_setting", side_effect=RuntimeError("db down")):
            self.assertEqual(get_trusted_sources(), [])


class TestGetTrustedDomains(unittest.TestCase):
    def test_extracts_domain_without_www(self):
        sources = [{"name": "Example", "url": "https://www.example.com/path"}]
        with patch("utils.web_access.get_trusted_sources", return_value=sources):
            self.assertEqual(get_trusted_domains(), ["example.com"])

    def test_empty_when_no_sources(self):
        with patch("utils.web_access.get_trusted_sources", return_value=[]):
            self.assertEqual(get_trusted_domains(), [])


if __name__ == "__main__":
    unittest.main()
