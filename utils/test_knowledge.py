"""
Тесты utils/knowledge.py — порог релевантности RAG (P2-2).

Раньше все вызовы шли с similarity_threshold=0.0, то есть фильтра не было вообще:
RPC возвращал ближайшие чанки всегда, даже полностью посторонние.
"""

from unittest.mock import patch

from utils import knowledge


class TestGetSimilarityThreshold:
    def test_reads_configured_value(self):
        with patch("database.queries.get_setting", return_value={"similarity_threshold": 0.6}):
            assert knowledge.get_similarity_threshold() == 0.6

    def test_falls_back_to_default_when_setting_missing(self):
        with patch("database.queries.get_setting", return_value=None):
            assert knowledge.get_similarity_threshold() == knowledge.DEFAULT_SIMILARITY_THRESHOLD

    def test_falls_back_when_setting_not_a_dict(self):
        with patch("database.queries.get_setting", return_value="oops"):
            assert knowledge.get_similarity_threshold() == knowledge.DEFAULT_SIMILARITY_THRESHOLD

    def test_falls_back_on_exception(self):
        with patch("database.queries.get_setting", side_effect=RuntimeError("db down")):
            assert knowledge.get_similarity_threshold() == knowledge.DEFAULT_SIMILARITY_THRESHOLD

    def test_ignores_out_of_range_values(self):
        # Порог вне [0,1] — опечатка нутрициолога; молча применять нельзя (1.5 = «ничего
        # не находим никогда», -1 = «фильтра нет»), поэтому откатываемся на дефолт.
        for bad in (1.5, -0.2, "0.8", True):
            with patch("database.queries.get_setting", return_value={"similarity_threshold": bad}):
                assert knowledge.get_similarity_threshold() == knowledge.DEFAULT_SIMILARITY_THRESHOLD

    def test_default_is_not_zero(self):
        # Суть P2-2: дефолт обязан фильтровать, иначе находка возвращается.
        assert knowledge.DEFAULT_SIMILARITY_THRESHOLD > 0


class TestSearchAppliesThreshold:
    def test_knowledge_base_uses_configured_threshold_by_default(self):
        with patch("utils.knowledge.get_embedding", return_value=[0.1] * 1536), \
             patch("utils.knowledge.get_similarity_threshold", return_value=0.75), \
             patch("database.queries.search_knowledge_base", return_value=[]) as rpc:
            knowledge.search_knowledge_base("вопрос")
        assert rpc.call_args.kwargs["similarity_threshold"] == 0.75

    def test_explicit_threshold_wins_over_configured(self):
        with patch("utils.knowledge.get_embedding", return_value=[0.1] * 1536), \
             patch("utils.knowledge.get_similarity_threshold", return_value=0.75), \
             patch("database.queries.search_knowledge_base", return_value=[]) as rpc:
            knowledge.search_knowledge_base("вопрос", similarity_threshold=0.9)
        assert rpc.call_args.kwargs["similarity_threshold"] == 0.9

    def test_explicit_zero_disables_filter_deliberately(self):
        # 0.0 остаётся валидным осознанным выбором — важно, чтобы None-логика его не съела.
        with patch("utils.knowledge.get_embedding", return_value=[0.1] * 1536), \
             patch("utils.knowledge.get_similarity_threshold", return_value=0.75), \
             patch("database.queries.search_knowledge_base", return_value=[]) as rpc:
            knowledge.search_knowledge_base("вопрос", similarity_threshold=0.0)
        assert rpc.call_args.kwargs["similarity_threshold"] == 0.0

    def test_client_documents_uses_configured_threshold_by_default(self):
        with patch("utils.knowledge.get_embedding", return_value=[0.1] * 1536), \
             patch("utils.knowledge.get_similarity_threshold", return_value=0.75), \
             patch("database.queries.search_client_documents", return_value=[]) as rpc:
            knowledge.search_client_documents("вопрос", "c1")
        assert rpc.call_args.kwargs["similarity_threshold"] == 0.75
