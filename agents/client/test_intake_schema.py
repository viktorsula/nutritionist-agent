"""
Тесты IntakeRecord v1 (Слайс 1): normalize / validate / parse_amount / адаптеры.
Чистые функции, без БД/LLM. Запуск: python -m pytest agents/client/test_intake_schema.py
"""

import unittest

from agents.client import intake_schema as s


class TestHelpers(unittest.TestCase):
    def test_parse_amount_grams(self):
        self.assertEqual(s.parse_amount("150 г"), {"value": 150.0, "unit": "g"})

    def test_parse_amount_pcs_and_ml(self):
        self.assertEqual(s.parse_amount("2 шт"), {"value": 2.0, "unit": "pcs"})
        self.assertEqual(s.parse_amount("300мл"), {"value": 300.0, "unit": "ml"})

    def test_parse_amount_comma_decimal(self):
        self.assertEqual(s.parse_amount("1,5 порции"), {"value": 1.5, "unit": "serving"})

    def test_parse_amount_no_number_is_none(self):
        self.assertIsNone(s.parse_amount("стакан"))
        self.assertIsNone(s.parse_amount(""))
        self.assertIsNone(s.parse_amount(None))

    def test_kbju_from_legacy_maps_old_keys(self):
        k = s.kbju_from_legacy({"calories": 200, "protein": 10, "fats": 5, "carbs": 30})
        self.assertEqual(k["kcal"], 200.0)
        self.assertEqual(k["protein_g"], 10.0)
        self.assertEqual(k["fat_g"], 5.0)
        self.assertEqual(k["carb_g"], 30.0)
        self.assertIsNone(k["sugar_g"])
        self.assertIsNone(k["fiber_g"])

    def test_kbju_from_legacy_survives_non_dict(self):
        # LLM иногда отдаёт kbju строкой/числом/списком — не должно падать (регресс прод-краша).
        for bad in ("неизвестно", 200, ["a"], None):
            k = s.kbju_from_legacy(bad)
            self.assertEqual(set(k.keys()), set(s.KBJU_KEYS))
            self.assertTrue(all(v is None for v in k.values()))

    def test_normalize_meal_item_with_string_kbju(self):
        # Ход из прод-лога: meal.items[].kbju пришёл строкой → normalize не должен падать.
        rec = s.normalize({
            "kind": "meal",
            "confidence": "high",
            "meal": {"meal_type": "lunch", "items": [{"name": "лазанья", "kbju": "много"}]},
        })
        self.assertEqual(rec["kind"], "meal")
        item = rec["meal"]["items"][0]
        self.assertEqual(item["name"], "лазанья")
        self.assertTrue(all(v is None for v in item["kbju"].values()))

    def test_infer_wellbeing_status(self):
        self.assertEqual(s.infer_wellbeing_status("нормально", ""), "ok")
        self.assertEqual(s.infer_wellbeing_status("плохо", "болит голова"), "bad")

    def test_sum_kbju_ignores_none(self):
        items = [
            {"kbju": {"kcal": 100, "protein_g": 5, "fat_g": None, "carb_g": None, "sugar_g": None, "fiber_g": None}},
            {"kbju": {"kcal": 50, "protein_g": None, "fat_g": 2, "carb_g": None, "sugar_g": None, "fiber_g": None}},
        ]
        total = s.sum_kbju(items)
        self.assertEqual(total["kcal"], 150.0)
        self.assertEqual(total["protein_g"], 5.0)
        self.assertEqual(total["fat_g"], 2.0)
        self.assertIsNone(total["carb_g"])


class TestNormalize(unittest.TestCase):
    def test_invalid_kind_becomes_none(self):
        r = s.normalize({"kind": "banana"})
        self.assertEqual(r["kind"], "none")
        self.assertEqual(r["schema_version"], s.SCHEMA_VERSION)

    def test_meal_total_computed_from_items(self):
        r = s.normalize({
            "kind": "meal", "source": "text",
            "meal": {"meal_type": "lunch", "items": [
                {"name": "курица", "kbju": {"kcal": 165, "protein_g": 31}},
                {"name": "рис", "kbju": {"kcal": 130, "carb_g": 28}},
            ]},
        })
        self.assertEqual(r["meal"]["total"]["kcal"], 295.0)
        self.assertEqual(r["meal"]["total"]["protein_g"], 31.0)
        self.assertEqual(r["meal"]["total"]["carb_g"], 28.0)
        # все ключи КБЖУ присутствуют
        self.assertEqual(set(r["meal"]["total"].keys()), set(s.KBJU_KEYS))

    def test_meal_item_amount_from_free_text(self):
        r = s.normalize({
            "kind": "meal",
            "meal": {"meal_type": "snack", "items": [{"name": "орехи", "amount": "30 г"}]},
        })
        self.assertEqual(r["meal"]["items"][0]["amount"], {"value": 30.0, "unit": "g"})

    def test_invalid_meal_type_defaults_all_day(self):
        r = s.normalize({"kind": "meal", "meal": {"meal_type": "brunch", "items": [{"name": "x"}]}})
        self.assertEqual(r["meal"]["meal_type"], "all_day")

    def test_water_and_weight_coerced(self):
        self.assertEqual(s.normalize({"kind": "water", "water_ml": "500"})["water_ml"], 500.0)
        self.assertEqual(s.normalize({"kind": "weight", "weight_kg": "80,5"})["weight_kg"], 80.5)

    def test_labs_drop_invalid(self):
        r = s.normalize({"kind": "lab", "labs": [
            {"indicator": "Холестерин", "value": "5,2", "unit": "mmol/L"},
            {"indicator": "", "value": 1},          # нет индикатора → выкинуть
            {"indicator": "глюкоза", "value": "n/a"},  # нет числа → выкинуть
        ]})
        self.assertEqual(len(r["labs"]), 1)
        self.assertEqual(r["labs"][0], {"indicator": "холестерин", "value": 5.2, "unit": "mmol/L", "measured_at": None})

    def test_does_not_mutate_input(self):
        src = {"kind": "water", "water_ml": "500"}
        s.normalize(src)
        self.assertEqual(src["water_ml"], "500")  # вход не изменён


class TestValidate(unittest.TestCase):
    def test_meal_without_items_needs_clarify(self):
        v = s.validate(s.normalize({"kind": "meal", "meal": {"items": []}}))
        self.assertTrue(v["needs_clarify"])

    def test_low_confidence_needs_clarify(self):
        rec = s.normalize({"kind": "meal", "confidence": "low",
                           "meal": {"items": [{"name": "суп"}]}})
        self.assertTrue(s.validate(rec)["needs_clarify"])

    def test_valid_meal_no_clarify(self):
        rec = s.normalize({"kind": "meal", "confidence": "high",
                           "meal": {"meal_type": "lunch", "items": [{"name": "суп"}]}})
        self.assertFalse(s.validate(rec)["needs_clarify"])

    def test_none_kind_clarify(self):
        self.assertTrue(s.validate(s.normalize({"kind": "none"}))["needs_clarify"])

    def test_water_zero_clarify(self):
        self.assertTrue(s.validate(s.normalize({"kind": "water", "water_ml": 0}))["needs_clarify"])

    def test_uncertainties_passed_through(self):
        rec = s.normalize({"kind": "meal", "confidence": "low",
                           "uncertainties": ["объём курицы", "рис отварной или жареный"],
                           "meal": {"items": [{"name": "курица"}]}})
        v = s.validate(rec)
        self.assertEqual(v["uncertainties"], ["объём курицы", "рис отварной или жареный"])


class TestAdapters(unittest.TestCase):
    def test_from_diary_meal(self):
        rec = s.from_diary_extract({"kind": "meal", "ingredients": ["курица", "рис"], "meal_type": "dinner"})
        self.assertEqual(rec["kind"], "meal")
        self.assertEqual([i["name"] for i in rec["meal"]["items"]], ["курица", "рис"])
        self.assertEqual(rec["meal"]["meal_type"], "dinner")
        self.assertEqual(rec["confidence"], "high")

    def test_from_diary_other_becomes_none_low(self):
        rec = s.from_diary_extract({"kind": "other"})
        self.assertEqual(rec["kind"], "none")
        self.assertEqual(rec["confidence"], "low")
        self.assertTrue(s.validate(rec)["needs_clarify"])

    def test_from_diary_weight_water(self):
        self.assertEqual(s.from_diary_extract({"kind": "weight", "weight_kg": "80"})["weight_kg"], 80.0)
        self.assertEqual(s.from_diary_extract({"kind": "water", "water_ml": 500})["water_ml"], 500.0)

    def test_from_diary_wellbeing_status_inferred(self):
        rec = s.from_diary_extract({"kind": "wellbeing", "wellbeing": {"answer": "плохо", "reason": "болит голова"}})
        self.assertEqual(rec["wellbeing"]["status"], "bad")
        self.assertEqual(rec["wellbeing"]["reason"], "болит голова")

    def test_from_diary_lab(self):
        rec = s.from_diary_extract({"kind": "lab", "labs": [{"indicator": "Холестерин", "value": "5.2", "unit": "mmol/L"}]})
        self.assertEqual(rec["labs"][0]["indicator"], "холестерин")
        self.assertEqual(rec["labs"][0]["value"], 5.2)

    def test_from_food_plate_maps_dish_items_kbju(self):
        fa = {
            "dish_name": "Курица с рисом",
            "confidence": "high",
            "ingredients": [
                {"name": "курица", "form": "отварная", "approx_amount": "150 г"},
                {"name": "рис", "form": "варёный", "approx_amount": "200 г"},
            ],
            "nutrition": {
                "items": [
                    {"name": "курица", "calories": 165, "protein": 31, "fats": 3, "carbs": 0},
                    {"name": "рис", "calories": 260, "protein": 5, "fats": 1, "carbs": 56},
                ],
                "total": {"calories": 425, "protein": 36, "fats": 4, "carbs": 56},
            },
        }
        rec = s.from_food_plate(fa, meal_type="lunch")
        self.assertEqual(rec["kind"], "meal")
        self.assertEqual(rec["source"], "photo")
        self.assertEqual(rec["meal"]["dish_name"], "Курица с рисом")
        self.assertEqual(rec["meal"]["meal_type"], "lunch")
        self.assertEqual(rec["meal"]["items"][0]["amount"], {"value": 150.0, "unit": "g"})
        self.assertEqual(rec["meal"]["items"][0]["kbju"]["kcal"], 165.0)
        self.assertEqual(rec["meal"]["total"]["kcal"], 425.0)
        self.assertEqual(rec["meal"]["total"]["carb_g"], 56.0)
        self.assertFalse(s.validate(rec)["needs_clarify"])

    def test_from_food_plate_low_confidence_clarify(self):
        rec = s.from_food_plate({"confidence": "low", "ingredients": []})
        self.assertTrue(s.validate(rec)["needs_clarify"])


class TestCoerceToRecord(unittest.TestCase):
    def test_new_format_meal_normalized_with_meal_type(self):
        parsed = {
            "kind": "meal", "confidence": "high", "uncertainties": [],
            "meal": {"meal_type": None, "items": [{"name": "рис", "kbju": {"kcal": 200}}]},
        }
        rec = s.coerce_to_record(parsed, source="text", meal_type="dinner")
        self.assertEqual(rec["kind"], "meal")
        self.assertEqual(rec["source"], "text")
        self.assertEqual(rec["meal"]["meal_type"], "dinner")  # форс meal_type
        self.assertEqual(rec["meal"]["total"]["kcal"], 200.0)

    def test_new_format_water_preserves_confidence_uncertainties(self):
        parsed = {"kind": "water", "water_ml": 500, "confidence": "medium", "uncertainties": ["точный объём"]}
        rec = s.coerce_to_record(parsed, source="text")
        self.assertEqual(rec["water_ml"], 500.0)
        self.assertEqual(rec["confidence"], "medium")
        self.assertEqual(rec["uncertainties"], ["точный объём"])

    def test_new_format_other_maps_to_none(self):
        rec = s.coerce_to_record({"kind": "other", "confidence": "low"}, source="text")
        self.assertEqual(rec["kind"], "none")

    def test_legacy_diary_meal_via_adapter(self):
        # старый формат: ingredients как список строк, без meal/confidence
        parsed = {"kind": "meal", "ingredients": ["курица", "рис"], "meal_type": "lunch"}
        rec = s.coerce_to_record(parsed, source="text", meal_type="lunch")
        self.assertEqual([i["name"] for i in rec["meal"]["items"]], ["курица", "рис"])

    def test_legacy_vision_via_adapter(self):
        # старый формат vision: ingredients как dict-и + nutrition, без meal
        parsed = {
            "dish_name": "Плов", "confidence": "high",
            "ingredients": [{"name": "рис", "form": "варёный", "approx_amount": "200 г"}],
            "nutrition": {"items": [{"name": "рис", "calories": 260}], "total": {"calories": 260}},
        }
        rec = s.coerce_to_record(parsed, source="photo", meal_type="lunch")
        self.assertEqual(rec["meal"]["dish_name"], "Плов")
        self.assertEqual(rec["meal"]["items"][0]["amount"], {"value": 200.0, "unit": "g"})
        self.assertEqual(rec["meal"]["total"]["kcal"], 260.0)

    def test_new_vision_meal_block(self):
        parsed = {
            "kind": "meal", "confidence": "high", "uncertainties": [],
            "meal": {"dish_name": "Омлет", "items": [{"name": "яйцо", "kbju": {"kcal": 150, "sugar_g": 1}}]},
        }
        rec = s.coerce_to_record(parsed, source="photo", meal_type="breakfast")
        self.assertEqual(rec["source"], "photo")
        self.assertEqual(rec["meal"]["dish_name"], "Омлет")
        self.assertEqual(rec["meal"]["total"]["sugar_g"], 1.0)


if __name__ == "__main__":
    unittest.main()
