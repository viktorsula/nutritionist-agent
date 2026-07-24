"""
Текст согласия на обработку персональных данных (LEGAL-1, Federal Law №2/2019 ОАЭ).

Гранулярные пункты (требование информированного согласия — не одна общая галочка):
- health_data — обработка данных о здоровье (вес/рост/заболевания/аллергии/анализы/дневник);
- telegram_channel — использование Telegram как канала связи.

Пункт про трансграничную передачу данных сознательно НЕ включён (решение владельца,
24.07.2026): не снимает юридический риск LEGAL-2 (локализация в ОАЭ, отложена на этап
пилота) — тот остаётся как есть, отдельное согласие на передачу его не покрывает и по
факту порождало вопросы клиентов без практической пользы.

Текст редактируется нутрициологом как обычная настройка (POST /nutritionist/setting,
ключ 'consent_text' — тот же механизм, что trusted_sources/llm_config), с дефолтом здесь на
случай, если ещё не задан. `version` — при изменении формулировки нутрициолог поднимает
версию, и клиенты с более старым consent_version в client_consents увидят гейт согласия
заново (см. ClientArea.tsx).
"""

from typing import Any, Dict

DEFAULT_CONSENT_TEXT: Dict[str, Any] = {
    "version": "1.0",
    "ru": {
        "health_data": (
            "Я даю согласие на сбор и обработку моих данных о здоровье (вес, рост, "
            "хронические заболевания, аллергии, результаты анализов, дневник питания) "
            "нутрициологом и ИИ-ассистентом для целей нутрициологического сопровождения."
        ),
        "telegram_channel": (
            "Я согласен(на) на использование Telegram в качестве канала связи для получения "
            "напоминаний и общения с ассистентом."
        ),
    },
    "en": {
        "health_data": (
            "I consent to the collection and processing of my health data (weight, height, "
            "chronic conditions, allergies, lab results, food diary) by the nutritionist and "
            "AI assistant for nutrition counselling purposes."
        ),
        "telegram_channel": (
            "I agree to use Telegram as a communication channel for reminders and "
            "conversations with the assistant."
        ),
    },
}


def get_consent_text() -> Dict[str, Any]:
    """
    Текущий текст согласия: DB-переопределение (system_settings.consent_text) целиком
    заменяет дефолт (та же логика, что trusted_sources), иначе — дефолт из этого модуля.
    """
    try:
        from database import queries

        override = queries.get_setting("consent_text")
        if isinstance(override, dict) and override.get("version"):
            return override
    except Exception:
        pass
    return DEFAULT_CONSENT_TEXT
