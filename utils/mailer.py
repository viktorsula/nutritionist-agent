"""
Отправка писем через SMTP (Gmail App Password) — best-effort канал в обход Supabase/Brevo.

Зачем: транзакционная почта Supabase (Brevo) без верифицированного домена не доставляет
письма. Этот модуль шлёт письмо напрямую через Gmail SMTP — например, временный пароль
клиента нутрициологу на его собственную почту. Если креды не заданы или SMTP отказал —
функция НЕ бросает исключение, а возвращает sent=False с причиной (вызывающий решает,
что показать пользователю; на экране пароль всё равно есть).

Ключи: GMAIL_USER, GMAIL_APP_PASSWORD из os.environ.get (НИКОГДА load_dotenv).
"""

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Dict

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587  # STARTTLS


def is_configured() -> bool:
    """True, если заданы оба ключа (GMAIL_USER + GMAIL_APP_PASSWORD)."""
    return bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD"))


def send_email(to: str, subject: str, body: str) -> Dict[str, object]:
    """
    Шлёт письмо через Gmail SMTP. Возвращает {'sent': bool, 'reason': str}.

    Best-effort: при отсутствии кредов → {'sent': False, 'reason': 'not_configured'};
    при ошибке SMTP → {'sent': False, 'reason': <текст>}. Исключение наружу не выбрасывается.
    """
    user = os.environ.get("GMAIL_USER")
    pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not user or not pw:
        return {"sent": False, "reason": "not_configured"}
    if not to:
        return {"sent": False, "reason": "no_recipient"}

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return {"sent": True, "reason": ""}
    except Exception as e:  # noqa: BLE001 — best-effort, причину возвращаем наверх
        logger.warning(f"send_email failed: {e!r}")
        return {"sent": False, "reason": str(e)}
