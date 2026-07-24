"""
Текст согласия на обработку персональных данных (LEGAL-1, Federal Law №2/2019 ОАЭ).

Гранулярные пункты (требование информированного согласия — не одна общая галочка):
- health_data — обработка данных о здоровье (вес/рост/заболевания/аллергии/анализы/дневник);
- telegram_channel — использование Telegram как канала связи;
- cross_border_transfer — трансграничная передача/хранение (актуально, пока LEGAL-2
  (локализация в ОАЭ) отложена решением владельца на этап пилота — см. diagnostic_report.md).

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
        "cross_border_transfer": (
            "Я согласен(на) на трансграничную передачу и хранение моих данных на серверах "
            "за пределами ОАЭ (используемых сервис-провайдерами платформы)."
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
        "cross_border_transfer": (
            "I agree to the cross-border transfer and storage of my data on servers located "
            "outside the UAE (used by the platform's service providers)."
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
