"""
Тесты ветки advice (1.5): приём фото холодильника → продукты → совет.
analyze_fridge и LLM мокаются.
"""

import unittest
from unittest.mock import patch

from agents.client import nutrition_agent as na


class TestGatherFridge(unittest.TestCase):
    def test_photo_with_products(self):
        state = {
            "message_type": "photo",
            "message": "что приготовить на ужин?",
            "metadata": {"image_bytes": b"x", "mime_type": "image/jpeg"},
        }
        with patch("utils.vision.analyze_fridge",
                   lambda *a, **k: {"products": ["курица", "яйца", "помидоры"]}):
            out = na._gather_fridge(state)
        self.assertIsNotNone(out)
        self.assertEqual(out["products"], ["курица", "яйца", "помидоры"])
        self.assertEqual(out["meal_type"], "dinner")
        self.assertEqual(state["food_items"], ["курица", "яйца", "помидоры"])

    def test_non_photo_returns_none(self):
        self.assertIsNone(na._gather_fridge({"message_type": "text", "message": "что съесть?"}))

    def test_no_image_bytes_returns_none(self):
        self.assertIsNone(na._gather_fridge({"message_type": "photo", "metadata": {}}))

    def test_empty_products_returns_none(self):
        state = {"message_type": "photo", "message": "", "metadata": {"image_bytes": b"x"}}
        with patch("utils.vision.analyze_fridge", lambda *a, **k: {"products": []}):
            self.assertIsNone(na._gather_fridge(state))


class TestFridgeBlock(unittest.TestCase):
    def test_block_has_products_and_meal(self):
        block = na._format_fridge_block({"products": ["курица", "рис"], "meal_type": "dinner"})
        self.assertIn("курица, рис", block)
        self.assertIn("ужин", block)
        self.assertIn("ТОЛЬКО из этих продуктов", block)


class TestBuildMessages(unittest.TestCase):
    def test_synthesizes_user_text_for_caption_less_fridge(self):
        msgs = na._build_messages(
            {"message": "", "conversation_history": []},
            "system",
            fridge={"products": ["яйца"], "meal_type": "breakfast"},
        )
        self.assertIn("фото продуктов", msgs[-1]["content"])

    def test_keeps_caption_when_present(self):
        msgs = na._build_messages(
            {"message": "что приготовить?", "conversation_history": []},
            "system",
            fridge={"products": ["яйца"], "meal_type": "breakfast"},
        )
        self.assertEqual(msgs[-1]["content"], "что приготовить?")


if __name__ == "__main__":
    unittest.main()
