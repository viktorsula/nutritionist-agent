"""
Тесты ядра ingestion (utils/ingestion.py).

Без сети: get_embedding и queries.insert_* мокаются. Проверяем извлечение текста,
чанкинг (размер/перекрытие/валидация) и запись чанков с корректным chunk_index.
"""

import unittest
from unittest.mock import patch

from utils import ingestion
from utils.ingestion import extract_text, chunk_text


class TestExtractText(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(extract_text(b"Hello \xd0\xbc\xd0\xb8\xd1\x80", "text/plain"), "Hello мир")

    def test_text_by_extension(self):
        self.assertEqual(extract_text(b"abc", "", "notes.md"), "abc")

    def test_empty_bytes(self):
        self.assertEqual(extract_text(b"", "text/plain"), "")

    def test_pdf_routes_to_pdf_extractor(self):
        with patch.object(ingestion, "_extract_pdf_text", return_value="PDF TEXT") as m:
            out = extract_text(b"%PDF-1.4 ...", "application/pdf", "labs.pdf")
        m.assert_called_once()
        self.assertEqual(out, "PDF TEXT")

    def test_unsupported_raises(self):
        with self.assertRaises(ValueError):
            extract_text(b"\x00\x01", "image/png", "photo.png")


class TestChunkText(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n  "), [])

    def test_short_single_chunk_normalized(self):
        self.assertEqual(chunk_text("a\n\n  b   c"), ["a b c"])

    def test_long_text_multiple_chunks_with_overlap(self):
        text = "x" * 2500
        chunks = chunk_text(text, chunk_size=1000, overlap=150)
        # шаг 850 → старты 0,850,1700,2550(стоп) => 3 чанка
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 1000 for c in chunks))
        # перекрытие: конец первого совпадает с началом второго
        self.assertEqual(chunks[0][-150:], chunks[1][:150])

    def test_no_empty_chunks(self):
        chunks = chunk_text("word " * 500, chunk_size=200, overlap=20)
        self.assertTrue(all(c.strip() for c in chunks))

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            chunk_text("text", chunk_size=0)
        with self.assertRaises(ValueError):
            chunk_text("text", chunk_size=100, overlap=100)


class TestIngest(unittest.TestCase):
    def setUp(self):
        self.emb = [0.0] * 1536

    def test_knowledge_base_writes_indexed_chunks(self):
        captured = []
        with patch.object(ingestion, "get_embedding", return_value=self.emb), \
             patch.object(ingestion.queries, "insert_knowledge_base_chunk",
                          side_effect=lambda c: captured.append(c)):
            n = ingestion.ingest_into_knowledge_base(
                document_id="doc-1", text="y" * 2500, source="Труд А",
                chunk_size=1000, overlap=150,
            )
        self.assertEqual(n, 3)
        self.assertEqual([c.chunk_index for c in captured], [0, 1, 2])
        self.assertTrue(all(c.document_id == "doc-1" for c in captured))
        self.assertTrue(all(c.source == "Труд А" for c in captured))
        self.assertTrue(all(c.embedding is self.emb for c in captured))

    def test_client_documents_writes_with_client_id(self):
        captured = []
        with patch.object(ingestion, "get_embedding", return_value=self.emb), \
             patch.object(ingestion.queries, "insert_client_document_chunk",
                          side_effect=lambda c: captured.append(c)):
            n = ingestion.ingest_into_client_documents(
                client_id="cl-1", document_id="doc-2", text="z" * 1200,
                chunk_size=1000, overlap=150,
            )
        self.assertEqual(n, 2)
        self.assertTrue(all(c.client_id == "cl-1" for c in captured))
        self.assertEqual([c.chunk_index for c in captured], [0, 1])

    def test_empty_text_writes_nothing(self):
        with patch.object(ingestion, "get_embedding", return_value=self.emb), \
             patch.object(ingestion.queries, "insert_knowledge_base_chunk") as m:
            n = ingestion.ingest_into_knowledge_base("doc-3", "   ")
        self.assertEqual(n, 0)
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
