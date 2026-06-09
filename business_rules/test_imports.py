"""
Тестовый файл для проверки импортов business_rules

Запуск: python business_rules/test_imports.py
"""

import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

print("=" * 60)
print("ТЕСТ ИМПОРТОВ business_rules")
print("=" * 60)

try:
    print("\n1. Импорт access_rules...")
    from business_rules.access_rules import check_access
    print("   ✅ check_access импортирован")

    print("\n2. Импорт medical_rules...")
    from business_rules.medical_rules import (
        check_allergies,
        check_medical_alerts,
        determine_routing
    )
    print("   ✅ check_allergies импортирован")
    print("   ✅ check_medical_alerts импортирован")
    print("   ✅ determine_routing импортирован")

    print("\n3. Импорт notification_rules...")
    from business_rules.notification_rules import (
        check_notification_allowed,
        is_within_allowed_hours,
        get_client_timezone
    )
    print("   ✅ check_notification_allowed импортирован")
    print("   ✅ is_within_allowed_hours импортирован")
    print("   ✅ get_client_timezone импортирован")

    print("\n4. Импорт через __init__.py...")
    from business_rules import (
        check_access,
        check_allergies,
        check_medical_alerts,
        determine_routing,
        check_notification_allowed,
        is_within_allowed_hours
    )
    print("   ✅ Все функции импортированы через __init__.py")

    print("\n" + "=" * 60)
    print("✅ ВСЕ ИМПОРТЫ УСПЕШНЫ!")
    print("=" * 60)
    print("\nСтруктура business_rules готова к использованию:")
    print("  • access_rules.py — проверка доступа")
    print("  • medical_rules.py — алерты и маршрутизация")
    print("  • notification_rules.py — правила уведомлений")
    print("\n")

except ImportError as e:
    print(f"\n❌ ОШИБКА ИМПОРТА: {e}")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ НЕОЖИДАННАЯ ОШИБКА: {e}")
    sys.exit(1)
