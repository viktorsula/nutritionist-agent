"""
Смоук-тест публичного API business_rules.

Раньше здесь лежал print-скрипт, который выполнялся на импорте и звал sys.exit(1) при
ошибке. Под pytest это давало не упавший тест, а INTERNALERROR со срывом ВСЕГО прогона —
то есть любое изменение импортов роняло весь набор вместо одного красного теста.
"""

import business_rules


def test_public_api_is_importable():
    from business_rules import (  # noqa: F401
        check_access,
        check_allergies,
        check_medical_alerts,
        determine_routing,
    )


def test_all_matches_actual_exports():
    # __all__ не должен обещать то, чего в пакете нет: после удаления notification_rules
    # (P2-4) такое рассогласование возникло бы незаметно — падало бы только у того, кто
    # сделает `from business_rules import *`.
    for name in business_rules.__all__:
        assert hasattr(business_rules, name), f"__all__ обещает {name}, которого нет"
