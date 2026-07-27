"""
Medical Rules — Медицинские проверки и алерты

Проверяет:
1. Аллергии (критично)
2. 4 типа медицинских алертов:
   - weight_increase (вес выше порога)
   - food_forbidden (запрещённый продукт)
   - food_incompatible (несочетаемые продукты через pgvector)
   - no_response (долгое отсутствие ответа)

   bad_wellbeing — НЕ здесь: детектируется напрямую в
   agents/client/intake_store.py::_persist_wellbeing в момент фиксации самочувствия
   (там же есть реальный payload {status, reason}). Раньше в этом модуле было
   параллельное, всегда падающее (TypeError, гасился общим except) determination
   через несуществующий event_type='wellbeing_checkin' — удалено как мёртвый код
   вместо починки: у него не было ни одного потребителя результата (P1-5).

3. Определяет маршрутизацию (к нутрициологу или только LLM)
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.queries import (
    get_client_profile,
    get_active_nutrition_plan,
    get_recent_measurements,
    get_conversations,
    get_setting,
)


# ════════════════════════════════════════════════════════════
# ПРОВЕРКА АЛЛЕРГИЙ
# ════════════════════════════════════════════════════════════

def _match_items(ingredients: List[str], watch_list: List[str]) -> List[str]:
    """
    Подстрочное совпадение продукта со списком (аллергены/непереносимости).

    ⚠️ Ограничение известно и открыто как P1-13: матчинг ТЕКСТОВЫЙ, а не смысловой —
    «кешью» не совпадёт с «орехи», «булгур» не совпадёт с «глютен». Смысловая проверка
    (шаг 2 P1-13) строится отдельно; здесь оставлен быстрый детерминированный слой,
    который ловит буквальные совпадения и работает без обращения к модели.
    """
    found: List[str] = []
    for ingredient in ingredients:
        item = (ingredient or "").lower()
        if not item:
            continue
        for entry in watch_list:
            e = (entry or "").lower().strip()
            if e and (e in item or item in e):
                found.append(entry)
                break
    return sorted(set(found))


def check_allergies(client_id: str, ingredients: List[str]) -> Dict[str, Any]:
    """
    Проверка ингредиентов на аллергены И непереносимости клиента (P1-13, шаг 1).

    Почему это два РАЗНЫХ списка, а не один (было до миграции 022):
    - аллергия — иммунный ответ, запрет абсолютный и дозонезависимый, опасны следовые
      количества → severity 'critical';
    - непереносимость — дозозависима и зависит от вида продукта (при лактазной
      недостаточности козий сыр часто допустим, коровье молоко — нет) → severity
      'medium', это сигнал нутрициологу на оценку, а не однозначный запрет.
    Пока оба состояния лежали в одном поле, отличить «нельзя вообще» от «зависит»
    было невозможно в принципе — данных для этого не существовало.

    Returns:
        {
            "has_allergen": bool,          # True только для НАСТОЯЩИХ аллергенов
            "allergens_found": List[str],
            "intolerances_found": List[str],
            "severity": "critical" | "medium" | "none" | "error",
            "message": str
        }
    """
    empty = {
        "has_allergen": False,
        "allergens_found": [],
        "intolerances_found": [],
        "severity": "none",
        "message": "",
    }
    if not ingredients:
        return dict(empty)

    try:
        profile = get_client_profile(client_id) or {}
        allergens = profile.get("allergies") or []
        intolerances = profile.get("intolerances") or []
        if not allergens and not intolerances:
            return dict(empty)

        found_allergens = _match_items(ingredients, allergens)
        found_intolerances = _match_items(ingredients, intolerances)

        if found_allergens:
            # Аллерген перекрывает всё остальное: это самый тяжёлый случай.
            return {
                "has_allergen": True,
                "allergens_found": found_allergens,
                "intolerances_found": found_intolerances,
                "severity": "critical",
                "message": (
                    f"⚠️ ВНИМАНИЕ! Обнаружен аллерген: {', '.join(found_allergens)}. "
                    "У вас аллергия на эти продукты!"
                ),
            }

        if found_intolerances:
            return {
                "has_allergen": False,
                "allergens_found": [],
                "intolerances_found": found_intolerances,
                "severity": "medium",
                "message": (
                    f"Отмечена непереносимость: {', '.join(found_intolerances)}. "
                    "Переносимость зависит от вида продукта и количества — "
                    "нутрициолог посмотрит и скажет точно."
                ),
            }

        return dict(empty)

    except Exception as e:
        # Сбой проверки — НЕ повод сказать «аллергенов нет»: возвращаем явную ошибку,
        # чтобы вызывающий видел разницу между «проверено, чисто» и «проверить не смогли».
        return {
            "has_allergen": False,
            "allergens_found": [],
            "intolerances_found": [],
            "severity": "error",
            "message": f"Ошибка при проверке аллергий: {str(e)}",
        }


# ════════════════════════════════════════════════════════════
# МЕДИЦИНСКИЕ АЛЕРТЫ
# ════════════════════════════════════════════════════════════

def check_medical_alerts(
    client_id: str,
    food_items: Optional[List[str]] = None,
    mode: str = "full_program"
) -> List[Dict[str, Any]]:
    """
    Проверка всех медицинских алертов

    Args:
        client_id: UUID клиента
        food_items: список продуктов (опционально)
        mode: режим работы клиента

    Returns:
        List[{
            "type": str,
            "severity": "low" | "medium" | "high" | "critical",
            "details": Dict,
            "message": str,
            "timestamp": str
        }]
    """
    alerts = []

    try:
        # [1] АЛЕРТ: weight_increase
        weight_alert = _check_weight_increase(client_id)
        if weight_alert:
            alerts.append(weight_alert)

        # [2] АЛЕРТ: food_forbidden (если есть food_items)
        if food_items:
            forbidden_alert = _check_food_forbidden(client_id, food_items)
            if forbidden_alert:
                alerts.append(forbidden_alert)

            # [3] АЛЕРТ: food_incompatible (через pgvector)
            incompatible_alert = _check_food_incompatible(client_id, food_items)
            if incompatible_alert:
                alerts.append(incompatible_alert)

        # [4] АЛЕРТ: no_response
        no_response_alert = _check_no_response(client_id)
        if no_response_alert:
            alerts.append(no_response_alert)

    except Exception as e:
        # Логируем ошибку, но не блокируем работу
        alerts.append({
            "type": "system_error",
            "severity": "low",
            "details": {"error": str(e)},
            "message": f"Ошибка при проверке алертов: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        })

    return alerts


def _within_days(earlier: Any, later: Any, max_days: int) -> bool:
    """True, если две даты (YYYY-MM-DD или ISO) различаются не более чем на max_days.
    При неразборчивых датах — не блокируем алерт (возвращаем True)."""
    try:
        d1 = datetime.fromisoformat(str(earlier)[:10])
        d2 = datetime.fromisoformat(str(later)[:10])
        return abs((d2 - d1).days) <= max_days
    except Exception:
        return True


def _get_alert_thresholds() -> Dict[str, Any]:
    """
    Глобальные пороги алертов (P1-4): system_settings.alert_thresholds — единый JSON
    (ключи weight_increase_kg/no_response_hours, см. docs/schema.sql сидинг). Раньше код
    читал get_system_setting('weight_increase_threshold_kg') — отдельную строку с
    неверным именем ключа, которой никогда не существовало, поэтому порог всегда падал
    на хардкод. Пустой словарь при ошибке/отсутствии — вызывающий код сам подставляет дефолт.
    """
    try:
        thresholds = get_setting('alert_thresholds')
        return thresholds if isinstance(thresholds, dict) else {}
    except Exception:
        return {}


def _check_weight_increase(client_id: str) -> Optional[Dict[str, Any]]:
    """Проверка резкого увеличения веса"""
    try:
        # Получить пороги
        profile = get_client_profile(client_id)
        custom_thresholds = profile.get('custom_alert_thresholds', {}) if profile else {}

        # Порог по умолчанию (из system_settings.alert_thresholds или hardcode).
        threshold_kg = custom_thresholds.get('weight_increase_threshold')
        if threshold_kg is None:
            threshold_kg = _get_alert_thresholds().get('weight_increase_kg', 1.0)

        # Вес теперь живёт в measurements (временной ряд). Сравниваем два
        # последних замера: текущий (свежий) против предыдущего.
        recent = get_recent_measurements(client_id, limit=2)
        if not recent or len(recent) < 2:
            return None

        # get_recent_measurements отдаёт свежие сверху: [0]=текущий, [1]=предыдущий
        current = recent[0].get('weight')
        previous = recent[1].get('weight')
        if current is None or previous is None:
            return None

        # Алерт — про резкий скачок «за день». При разрежённых замерах (разрыв
        # в несколько дней) большой набор веса — не дневной спайк, не алертим.
        max_gap_days = 3
        if not _within_days(recent[1].get('measured_at'), recent[0].get('measured_at'), max_gap_days):
            return None

        weight_change = current - previous

        if weight_change > threshold_kg:
            return {
                "type": "weight_increase",
                "severity": "high" if weight_change > threshold_kg * 1.5 else "medium",
                "details": {
                    "previous_weight": previous,
                    "current_weight": current,
                    "change_kg": round(weight_change, 2),
                    "threshold_kg": threshold_kg
                },
                "message": f"Зафиксировано увеличение веса на {round(weight_change, 2)} кг между последними замерами (порог: {threshold_kg} кг).",
                "timestamp": datetime.utcnow().isoformat()
            }

        return None

    except Exception:
        return None


def _check_food_forbidden(client_id: str, food_items: List[str]) -> Optional[Dict[str, Any]]:
    """Проверка запрещённых продуктов из плана питания"""
    try:
        plan = get_active_nutrition_plan(client_id)

        if not plan:
            return None

        # Назначения нутрициолога лежат в plan_json (редактор пишет туда); фолбэк на
        # верхний уровень — для старых записей/тестов (тот же паттерн, что в _plan_view).
        plan_json = plan.get('plan_json') if isinstance(plan.get('plan_json'), dict) else {}
        restrictions = plan_json.get('restrictions') or plan.get('restrictions')

        if not restrictions:
            return None

        # Проверяем каждый продукт
        forbidden_found = []
        for item in food_items:
            item_lower = item.lower()
            for restriction in restrictions:
                if restriction.lower() in item_lower or item_lower in restriction.lower():
                    forbidden_found.append(item)
                    break

        if forbidden_found:
            return {
                "type": "food_forbidden",
                "severity": "high",
                "details": {
                    "forbidden_items": forbidden_found,
                    "restrictions": restrictions
                },
                "message": f"⚠️ Обнаружены запрещённые продукты: {', '.join(forbidden_found)}",
                "timestamp": datetime.utcnow().isoformat()
            }

        return None

    except Exception:
        return None


# Похожесть чанка базы знаний на запрос про сочетание продуктов, ниже которой не считаем
# находку значимой (P1-3). Выше дефолтного порога RAG (0.0, см. P2-2) — здесь важна
# точность (алерт нутрициологу), а не полнота выдачи.
_FOOD_INCOMPATIBLE_SIMILARITY_THRESHOLD = 0.75


def _check_food_incompatible(client_id: str, food_items: List[str]) -> Optional[Dict[str, Any]]:
    """
    Проверка несочетаемых продуктов через pgvector-поиск по базе знаний нутрициолога
    (P1-3). Несовместимость — свойство КОМБИНАЦИИ продуктов, поэтому при одном
    продукте в приёме проверка не имеет смысла.

    Находка — семантическое совпадение с материалом о несочетаемости в базе знаний,
    не подтверждённый факт: это сигнал нутрициологу на просмотр, а не автономный
    диагноз. Качество зависит от наполнения базы знаний — при пустой/бедной базе
    просто ничего не находится (return None), это ожидаемо, не ошибка.
    """
    if not food_items or len(food_items) < 2:
        return None

    try:
        from utils.knowledge import search_knowledge_base

        query = "сочетание продуктов: " + ", ".join(food_items)
        chunks = search_knowledge_base(
            query, match_count=1, similarity_threshold=_FOOD_INCOMPATIBLE_SIMILARITY_THRESHOLD,
        )
        if not chunks:
            return None

        chunk = chunks[0]
        excerpt = (chunk.get("chunk_text") or "").strip()
        if not excerpt:
            return None

        return {
            "type": "food_incompatible",
            "severity": "medium",
            "details": {
                "food_items": food_items,
                "similarity": chunk.get("similarity"),
                "source": chunk.get("source"),
            },
            "message": (
                f"Возможное несочетание продуктов ({', '.join(food_items)}) — "
                f"похожий материал в базе знаний: {excerpt[:280]}"
            ),
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception:
        return None


def _check_no_response(client_id: str) -> Optional[Dict[str, Any]]:
    """Проверка долгого отсутствия ответа от клиента"""
    try:
        # Порог отсутствия ответа (часов) — из system_settings.alert_thresholds (P1-4).
        threshold_hours = _get_alert_thresholds().get('no_response_hours', 48)

        # Получить последнее сообщение клиента
        conversations = get_conversations(client_id=client_id, limit=10)

        if not conversations:
            return None

        # Найти последнее сообщение от клиента (role='client')
        client_messages = [c for c in conversations if c.get('role') == 'client']

        if not client_messages:
            return None

        last_message = client_messages[0]
        last_timestamp = last_message.get('message_timestamp') or last_message.get('created_at')

        if not last_timestamp:
            return None

        # Парсим timestamp
        if isinstance(last_timestamp, str):
            last_time = datetime.fromisoformat(last_timestamp.replace('Z', '+00:00'))
        else:
            last_time = last_timestamp

        hours_since = (datetime.utcnow().replace(tzinfo=None) - last_time.replace(tzinfo=None)).total_seconds() / 3600

        if hours_since > threshold_hours:
            return {
                "type": "no_response",
                "severity": "medium" if hours_since < threshold_hours * 2 else "high",
                "details": {
                    "hours_since_last_message": round(hours_since, 1),
                    "threshold_hours": threshold_hours,
                    "last_message_time": last_timestamp
                },
                "message": f"Клиент не отвечает уже {round(hours_since, 1)} часов (порог: {threshold_hours}ч)",
                "timestamp": datetime.utcnow().isoformat()
            }

        return None

    except Exception:
        return None


# ════════════════════════════════════════════════════════════
# МАРШРУТИЗАЦИЯ
# ════════════════════════════════════════════════════════════

def determine_routing(alerts: List[Dict], mode: str) -> Dict[str, Any]:
    """
    Определяет куда направить сообщение на основе алертов и режима

    Args:
        alerts: список алертов от check_medical_alerts()
        mode: 'full_program' | 'ai_support'

    Returns:
        {
            "route_to": "llm" | "nutritionist" | "both",
            "notify_nutritionist": bool,
            "block_llm": bool,
            "alerts": List[Alert],
            "priority": "low" | "medium" | "high" | "critical",
            "nutritionist_message": str (если notify=True),
            "llm_context": Dict (дополнительный контекст для LLM)
        }
    """

    # Нет алертов → всегда в LLM
    if not alerts:
        return {
            "route_to": "llm",
            "notify_nutritionist": False,
            "block_llm": False,
            "alerts": [],
            "priority": "low",
            "llm_context": {}
        }

    # Определяем максимальный severity
    severities = [a["severity"] for a in alerts]
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    max_severity = max(severities, key=lambda s: severity_order.get(s, 0))

    # ════════════════════════════════════════════
    # РЕЖИМ: AI-ПОДДЕРЖКА (без нутрициолога)
    # ════════════════════════════════════════════
    if mode == 'ai_support':
        # ВСЕ алерты обрабатывает только LLM
        # Нутрициолог НИКОГДА не уведомляется
        return {
            "route_to": "llm",
            "notify_nutritionist": False,
            "block_llm": False,
            "alerts": alerts,
            "priority": max_severity,
            "llm_context": {
                "mode": "ai_support",
                "handle_alerts_independently": True
            }
        }

    # ════════════════════════════════════════════
    # РЕЖИМ: ПОЛНАЯ ПРОГРАММА (с нутрициологом)
    # ════════════════════════════════════════════
    if mode == 'full_program':

        # КРИТИЧНЫЕ АЛЕРТЫ (high/critical)
        if max_severity in ['high', 'critical']:
            return {
                "route_to": "both",  # И нутрициологу, И в LLM
                "notify_nutritionist": True,
                "block_llm": False,  # LLM тоже отвечает клиенту
                "alerts": alerts,
                "priority": max_severity,
                "nutritionist_message": _format_alert_for_nutritionist(alerts, mode),
                "llm_context": {
                    "mode": "full_program",
                    "nutritionist_notified": True,  # ← КЛЮЧЕВОЙ ФЛАГ
                    "alert_severity": max_severity,
                    "instruction": (
                        "Нутрициолог уже уведомлён о ситуации и свяжется с клиентом в ближайшее время. "
                        "Включи эту информацию в свой ответ и предоставь клиенту полезные рекомендации."
                    )
                }
            }

        # СРЕДНИЕ/НИЗКИЕ АЛЕРТЫ (low/medium)
        else:
            return {
                "route_to": "llm",
                "notify_nutritionist": False,
                "block_llm": False,
                "alerts": alerts,
                "priority": max_severity,
                "llm_context": {
                    "mode": "full_program",
                    "nutritionist_notified": False,
                    "alert_severity": max_severity
                }
            }

    # Fallback (не должны попадать)
    return {
        "route_to": "llm",
        "notify_nutritionist": False,
        "block_llm": False,
        "alerts": alerts,
        "priority": max_severity,
        "llm_context": {}
    }


def _format_alert_for_nutritionist(alerts: List[Dict], mode: str) -> str:
    """
    Форматирует алерты для уведомления нутрициологу

    Args:
        alerts: список алертов
        mode: режим работы клиента

    Returns:
        Форматированное сообщение для нутрициолога
    """
    if not alerts:
        return ""

    lines = [
        "🚨 КРИТИЧНЫЙ АЛЕРТ ОТ КЛИЕНТА",
        f"Режим: {mode}",
        f"Время: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Обнаруженные проблемы:"
    ]

    for i, alert in enumerate(alerts, 1):
        severity_emoji = {
            "low": "ℹ️",
            "medium": "⚠️",
            "high": "🔴",
            "critical": "🚨"
        }.get(alert['severity'], "•")

        lines.append(f"{severity_emoji} {i}. {alert['type'].upper()}")
        lines.append(f"   Важность: {alert['severity']}")
        lines.append(f"   {alert['message']}")

        # Добавляем детали
        if alert.get('details'):
            details = alert['details']
            for key, value in details.items():
                if key not in ['timestamp']:
                    lines.append(f"   - {key}: {value}")

        lines.append("")

    lines.append("Требуется ваше внимание к этой ситуации.")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════
# УТИЛИТЫ
# ════════════════════════════════════════════════════════════

def get_highest_severity(severities: List[str]) -> str:
    """Определяет наивысший severity из списка"""
    severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return max(severities, key=lambda s: severity_order.get(s, 0))
