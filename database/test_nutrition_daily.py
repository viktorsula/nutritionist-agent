"""
get_nutrition_daily: суточная агрегация питания из client_events (для графиков питания, C1).
Суммирует calories_logged.total (ккал/Б/Ж/У/сахар) и water_logged.water_ml по датам.
"""

from unittest.mock import patch

from database import queries


def test_get_nutrition_daily_aggregates_by_day():
    rows = [
        {"event_type": "calories_logged", "event_date": "2026-07-01T08:00:00",
         "payload_json": {"total": {"kcal": 300, "protein_g": 10, "fat_g": 5, "carb_g": 40, "sugar_g": 8}}},
        {"event_type": "calories_logged", "event_date": "2026-07-01T13:00:00",
         "payload_json": {"total": {"kcal": 500, "protein_g": 20, "fat_g": 15, "carb_g": 50, "sugar_g": 12}}},
        {"event_type": "water_logged", "event_date": "2026-07-01T09:00:00",
         "payload_json": {"water_ml": 250}},
        {"event_type": "water_logged", "event_date": "2026-07-02T10:00:00",
         "payload_json": {"water_ml": 500}},
    ]
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=rows):
        out = queries.get_nutrition_daily("cid", days=7)

    assert [d["date"] for d in out] == ["2026-07-01", "2026-07-02"]  # по возрастанию
    d1 = out[0]
    assert d1["kcal"] == 800
    assert d1["protein_g"] == 30
    assert d1["carb_g"] == 90
    assert d1["sugar_g"] == 20
    assert d1["water_ml"] == 250
    # день только с водой — макросы нули
    assert out[1] == {"date": "2026-07-02", "kcal": 0.0, "protein_g": 0.0, "fat_g": 0.0,
                      "carb_g": 0.0, "sugar_g": 0.0, "water_ml": 500}


def test_get_nutrition_daily_tolerates_missing_total_and_bad_values():
    rows = [
        {"event_type": "calories_logged", "event_date": "2026-07-01T08:00:00",
         "payload_json": {}},  # нет total
        {"event_type": "calories_logged", "event_date": "2026-07-01T12:00:00",
         "payload_json": {"total": {"kcal": None, "protein_g": "x", "carb_g": 30}}},  # мусор
        {"event_type": "water_logged", "event_date": "", "payload_json": {"water_ml": 100}},  # без даты
    ]
    with patch("database.queries._service_client"), \
         patch("database.queries._extract_data", return_value=rows):
        out = queries.get_nutrition_daily("cid", days=7)
    assert len(out) == 1
    assert out[0]["carb_g"] == 30
    assert out[0]["kcal"] == 0.0  # None → 0, "x" → 0
