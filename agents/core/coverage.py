"""
Наблюдаемость покрытия LLM-оркестраторами (Ф3, Шаг 0).

Каждый ход клиента/нутрициолога помечается ОДНИМ путём:
- "orchestrator"    — ход обработал LLM-оркестратор (цель миграции);
- "graph_flag_off"  — оркестратор для этого хода выключен (флаг/белый список/неподдерж. тип) —
                      это НОРМА (клиент/нутрициолог ещё не enrolled), не сбой;
- "graph_fallback"  — оркестратор ПЫТАЛСЯ, но упал (LLMUnavailable/ошибка) → откат на граф.
                      ВОТ ЭТО должно быть НОЛЬ на периоде обкатки (критерий чистки графа, Ф3).

Пишем структурную строку в лог (стабильный префикс `COVERAGE` — тривиально грепается в Render,
чтобы посчитать покрытие/фолбэки за период) и держим in-memory счётчики (для быстрой сводки внутри
процесса и тестов). Это ТОЛЬКО наблюдение — поведение хода не меняется.

Критерии чистки графа (Ф3) проверяются по этим данным: за период
`graph_fallback == 0`, доля `orchestrator` растёт к 100% по мере снятия белых списков.
"""

import logging
import threading
from collections import Counter
from typing import Dict, Optional

logger = logging.getLogger(__name__)

PATHS = ("orchestrator", "graph_flag_off", "graph_fallback")

_counter: "Counter[tuple]" = Counter()
_lock = threading.Lock()


def record_turn(role: str, path: str, reason: Optional[str] = None) -> None:
    """
    Зафиксировать путь одного хода. `role` — 'client'|'nutritionist'. Неизвестный `path`
    трактуем консервативно как `graph_fallback` (чтобы не занизить проблему).
    """
    if path not in PATHS:
        path = "graph_fallback"
    with _lock:
        _counter[(role, path)] += 1
    extra = f" reason={reason}" if reason else ""
    logger.info(f"COVERAGE role={role} path={path}{extra}")


def snapshot() -> Dict[str, int]:
    """Копия счётчиков в виде {'role:path': n} — для сводки/тестов."""
    with _lock:
        return {f"{role}:{path}": n for (role, path), n in _counter.items()}


def reset() -> None:
    """Сброс счётчиков (для тестов)."""
    with _lock:
        _counter.clear()
