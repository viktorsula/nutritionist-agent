"""
Business Rules — Детерминированный слой бизнес-логики

Обрабатывает критические ситуации ДО вызова LLM:
- Проверка доступа (анкета, оплата, статусы)
- Медицинские проверки (алерты, аллергии)

Все функции возвращают Dict с чёткими инструкциями для router.py
"""

from .access_rules import check_access
from .medical_rules import (
    check_allergies,
    check_medical_alerts,
    determine_routing
)

__all__ = [
    # Access control
    "check_access",

    # Medical checks
    "check_allergies",
    "check_medical_alerts",
    "determine_routing",
]
