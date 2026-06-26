"""
Vision — анализ изображений через Gemini 1.5 Flash (Этап 6)

Назначение:
- Распознавание блюда по фото тарелки + оценка КБЖУ (UC-2, в MVP).
- Распознавание продуктов по фото холодильника (UC-3, v1.1).

Архитектура:
1. analyze_image(image_bytes, prompt) → произвольный анализ фото (сырой текст)
2. analyze_food_plate(image_bytes) → структурированный КБЖУ-результат (dict)

Ключи: GOOGLE_API_KEY из os.environ.get (НИКОГДА load_dotenv).
Модель: gemini-1.5-flash (бесплатно, 1500 req/день).

TODO v1.1:
- analyze_fridge() — фото холодильника → варианты блюд
- Кэширование результатов по хэшу изображения
"""

import os
import json
import logging
from typing import Any, Dict, List, Optional

# Импорт SDK (устанавливается через requirements.txt)
try:
    import google.generativeai as genai
except ImportError:
    genai = None

from prompts import load_prompt

logger = logging.getLogger(__name__)


# ========================================
# КОНФИГУРАЦИЯ
# ========================================

VISION_MODEL = "gemini-1.5-flash"
"""Модель vision. Flash — бесплатно, 1500 запросов/день."""


# ========================================
# БАЗОВЫЙ АНАЛИЗ ИЗОБРАЖЕНИЯ
# ========================================

def analyze_image(
    image_bytes: bytes,
    prompt: str,
    mime_type: str = "image/jpeg",
    model: Optional[str] = None,
) -> str:
    """
    Анализирует изображение по текстовому промпту через Gemini Flash.

    Args:
        image_bytes: Бинарное содержимое изображения
        prompt: Что нужно сделать с изображением
        mime_type: MIME-тип ('image/jpeg', 'image/png', ...)
        model: Переопределение модели (по умолчанию gemini-1.5-flash)

    Returns:
        Текстовый ответ модели

    Raises:
        RuntimeError: Если SDK не установлен или нет GOOGLE_API_KEY
        ValueError: Если изображение пустое
    """
    if genai is None:
        raise RuntimeError(
            "Google Generative AI SDK не установлен. "
            "Установите: pip install google-generativeai"
        )

    if not image_bytes:
        raise ValueError("analyze_image(): передано пустое изображение")

    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY не найден в переменных окружения. "
            "Добавьте в .env или Render Environment Variables"
        )

    try:
        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model or VISION_MODEL)

        response = gen_model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": image_bytes},
        ])

        return response.text

    except Exception as e:
        logger.error(f"Gemini Vision error: {e}")
        raise RuntimeError(f"Ошибка анализа изображения: {str(e)}") from e


# ========================================
# АНАЛИЗ ФОТО ТАРЕЛКИ (КБЖУ) — UC-2
# ========================================

def analyze_food_plate(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Распознаёт состав блюда на фото тарелки (UC-2).

    Приоритет: ингредиенты, их форма приготовления и количество (для business_rules:
    аллергии, запрещённые продукты, сочетаемость). КБЖУ — вторичная, грубая оценка.

    Args:
        image_bytes: Бинарное содержимое фото
        mime_type: MIME-тип изображения

    Returns:
        {
            "dish_name": str,
            "ingredients": [{"name", "form", "approx_amount", "category"}],  # первично
            "nutrition": {
                "items": [{"name", "calories", "protein", "fats", "carbs"}],
                "total": {"calories", "protein", "fats", "carbs"}
            },                                                               # вторично
            "confidence": str,
            "notes": str,
            "raw": str            # сырой ответ модели (для отладки)
        }
        При ошибке парсинга — ingredients=[], в notes причина, в raw — ответ модели.
    """
    raw = analyze_image(image_bytes, load_prompt("system/vision_food_plate"), mime_type=mime_type)

    parsed = _safe_parse_json(raw)

    empty_nutrition = {
        "items": [],
        "total": {"calories": 0, "protein": 0, "fats": 0, "carbs": 0},
    }

    if parsed is None:
        logger.warning("analyze_food_plate: не удалось распарсить JSON из ответа модели")
        return {
            "dish_name": "",
            "ingredients": [],
            "nutrition": empty_nutrition,
            "confidence": "low",
            "notes": "Не удалось распознать блюдо автоматически.",
            "raw": raw,
        }

    parsed.setdefault("dish_name", "")
    parsed.setdefault("ingredients", [])
    parsed.setdefault("nutrition", empty_nutrition)
    parsed.setdefault("confidence", "medium")
    parsed.setdefault("notes", "")
    parsed["raw"] = raw

    return parsed


# ========================================
# КЛАССИФИКАЦИЯ ТИПА ИЗОБРАЖЕНИЯ + АНАЛИЗЫ С ДОКУМЕНТА
# ========================================

def classify_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Грубо классифицирует изображение: 'food' | 'document' | 'other'.

    При ошибке/неоднозначности → 'food' (исторический путь обработки фото).
    """
    try:
        raw = analyze_image(image_bytes, load_prompt("system/vision_image_kind"), mime_type=mime_type)
        kind = (_safe_parse_json(raw) or {}).get("kind")
        return kind if kind in ("food", "document", "other") else "food"
    except Exception as e:
        logger.warning(f"classify_image failed: {e}")
        return "food"


def analyze_lab_document(image_bytes: bytes, mime_type: str = "image/jpeg") -> Dict[str, Any]:
    """
    Извлекает числовые показатели анализов с фото документа.

    Returns:
        {"labs": [{"indicator","value","unit"}], "measured_at": str,
         "confidence": str, "notes": str, "raw": str}
        При ошибке парсинга — labs=[], причина в notes.
    """
    raw = analyze_image(image_bytes, load_prompt("system/vision_lab_document"), mime_type=mime_type)
    parsed = _safe_parse_json(raw)
    if parsed is None:
        logger.warning("analyze_lab_document: не удалось распарсить JSON из ответа модели")
        return {
            "labs": [],
            "measured_at": "",
            "confidence": "low",
            "notes": "Не удалось распознать документ автоматически.",
            "raw": raw,
        }
    parsed.setdefault("labs", [])
    parsed.setdefault("measured_at", "")
    parsed.setdefault("confidence", "medium")
    parsed.setdefault("notes", "")
    parsed["raw"] = raw
    return parsed


def extract_ingredient_names(food_analysis: Dict[str, Any]) -> List[str]:
    """
    Достаёт плоский список названий ингредиентов из результата analyze_food_plate().

    Удобно для передачи в business_rules (check_allergies, food_forbidden и т.п.).
    """
    ingredients = food_analysis.get("ingredients", []) or []
    names = []
    for ing in ingredients:
        if isinstance(ing, dict):
            name = ing.get("name")
            if name:
                names.append(name)
        elif isinstance(ing, str):
            names.append(ing)
    return names


# ========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ========================================

def _safe_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Безопасно извлекает JSON из ответа модели.

    Учитывает, что модель может обернуть JSON в ```json ... ``` или добавить текст.
    """
    if not text:
        return None

    cleaned = text.strip()

    # Снять markdown-обёртку ```json ... ```
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    # Попробовать как есть
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Вырезать первый JSON-объект по фигурным скобкам
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            return None

    return None
