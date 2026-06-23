"""
Аутентификация для веб-API (Фронт Фаза 1)

Проверяет Supabase JWT и резолвит прикладного пользователя из БД:
- verify_access_token(token) — валидирует токен через Supabase Auth (anon-клиент),
  возвращает auth_id/email.
- resolve_app_user(auth_id) — читает users (роль) и clients (client_id + статусы)
  под service-ключом.
- authenticate(token) — связка: токен → прикладной пользователь.

Принцип безопасности: роль и client_id берутся ИЗ БД по auth_id из проверенного
токена, а не из тела запроса — клиент не может выдать себя за другого/сменить роль.
"""

import logging
from typing import Any, Dict, Optional

from database.client import get_supabase_service_client

logger = logging.getLogger(__name__)


def verify_access_token(access_token: str) -> Optional[Dict[str, Any]]:
    """Валидирует Supabase access token. Возвращает {auth_id, email} или None.

    Используем service-клиент, а НЕ anon: личность берётся из самого JWT
    (get_user проверяет токен на стороне Supabase), apikey лишь авторизует запрос.
    Так бэкенду не нужен SUPABASE_ANON_KEY — раньше его отсутствие давало 401 на /me.
    """
    if not access_token:
        return None
    try:
        sb = get_supabase_service_client()
        resp = sb.auth.get_user(access_token)
        user = getattr(resp, "user", None)
        if not user or not getattr(user, "id", None):
            return None
        return {"auth_id": user.id, "email": getattr(user, "email", None)}
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        return None


def resolve_app_user(auth_id: str) -> Optional[Dict[str, Any]]:
    """
    Резолвит прикладного пользователя по auth_id (service-ключ).

    Returns:
        {auth_id, user_id, role, email, client_id,
         name, client_status, payment_status, access_status, language, timezone}
        или None, если пользователь не зарегистрирован в users.
    """
    try:
        sb = get_supabase_service_client()
        urows = sb.table("users").select("*").eq("auth_id", auth_id).limit(1).execute()
        users = getattr(urows, "data", None) or []
        if not users:
            return None
        u = users[0]

        info: Dict[str, Any] = {
            "auth_id": auth_id,
            "user_id": u.get("id"),
            "role": u.get("role"),
            "email": u.get("email"),
            "client_id": None,
            "web_allowed": True,   # нутрициолог/observer — всегда; для клиента уточняется ниже
            "web_message": "",
            "tier": None,
        }

        if u.get("role") == "client":
            crows = (
                sb.table("clients")
                .select("id,name,client_status,payment_status,access_status,language,timezone")
                .eq("user_id", u["id"])
                .limit(1)
                .execute()
            )
            clients = getattr(crows, "data", None) or []
            if clients:
                c = clients[0]
                info.update({
                    "client_id": c.get("id"),
                    "name": c.get("name"),
                    "client_status": c.get("client_status"),
                    "payment_status": c.get("payment_status"),
                    "access_status": c.get("access_status"),
                    "language": c.get("language"),
                    "timezone": c.get("timezone"),
                })
                # Допуск в веб-кабинет и тариф — через бизнес-правила.
                try:
                    from business_rules.access_rules import check_web_access, get_access_tier
                    web = check_web_access(c["id"])
                    info["web_allowed"] = web.get("allowed", False)
                    info["web_message"] = web.get("message_for_client", "")
                    info["tier"] = get_access_tier(c)
                except Exception as e:
                    logger.warning(f"web access check failed: {e}")
                    info["web_allowed"] = False
                    info["web_message"] = "Не удалось проверить доступ. Обратитесь к нутрициологу."
            else:
                # Роль client, но нет строки clients — в кабинет не пускаем.
                info["web_allowed"] = False
                info["web_message"] = "Профиль клиента не найден. Обратитесь к нутрициологу."

        return info
    except Exception as e:
        logger.error(f"resolve_app_user failed: {e}")
        return None


def authenticate(access_token: str) -> Optional[Dict[str, Any]]:
    """Токен → прикладной пользователь (роль + client_id) или None."""
    token_info = verify_access_token(access_token)
    if not token_info:
        return None
    return resolve_app_user(token_info["auth_id"])


def invite_client_account(
    email: str,
    name: str,
    timezone: str = "Asia/Dubai",
    language: str = "ru",
    actor_user_id: Optional[str] = None,
    payment_status: str = "trial",
    client_status: str = "onboarding",
    paid_until: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Создаёт аккаунт клиента (вызывает нутрициолог): приглашение в Supabase Auth +
    строки в users (role='client') и clients. Под service-ключом (admin).

    Нутрициолог задаёт стартовые статусы:
    - payment_status: 'active' (оплачено) | 'inactive' (не оплачено) | 'trial'.
      'inactive' блокирует вход в кабинет (check_web_access).
    - client_status: 'active' (режим «полный», сопровождение нутрициолога) |
      'onboarding' (режим «базовый», кабинет + ИИ). Тариф выводится из статуса.
    - paid_until: дата окончания оплаченного периода ('YYYY-MM-DD' или None).

    Клиент получает письмо-приглашение и задаёт пароль / входит по коду.
    Возвращает {auth_id, user_id, client_id, email}.
    Бросает исключение при ошибке (например, email уже существует).
    """
    sb = get_supabase_service_client()

    # 1. Пригласить пользователя в Supabase Auth (создаёт auth-аккаунт, шлёт письмо)
    invite = sb.auth.admin.invite_user_by_email(email)
    auth_user = getattr(invite, "user", None)
    auth_id = getattr(auth_user, "id", None)
    if not auth_id:
        raise RuntimeError("Supabase invite did not return a user id")

    # 2. Строка в users (роль client)
    urow = sb.table("users").insert({
        "auth_id": auth_id,
        "role": "client",
        "email": email,
    }).execute()
    users = getattr(urow, "data", None) or []
    if not users:
        raise RuntimeError("Failed to create users row")
    user_id = users[0]["id"]

    # 3. Строка в clients (со стартовыми статусами от нутрициолога)
    crow = sb.table("clients").insert({
        "user_id": user_id,
        "name": name,
        "email": email,
        "timezone": timezone,
        "language": language,
        "payment_status": payment_status,
        "client_status": client_status,
        "paid_until": paid_until,
    }).execute()
    clients = getattr(crow, "data", None) or []
    if not clients:
        raise RuntimeError("Failed to create clients row")
    client_id = clients[0]["id"]

    # 4. Аудит (best-effort)
    try:
        from database import queries
        queries.write_audit_log(
            actor_type="nutritionist",
            actor_id=actor_user_id,
            action="create_client",
            entity_type="client",
            entity_id=client_id,
            new_value={
                "email": email,
                "name": name,
                "payment_status": payment_status,
                "client_status": client_status,
                "paid_until": paid_until,
            },
        )
    except Exception as e:
        logger.warning(f"audit log for create_client failed: {e}")

    return {"auth_id": auth_id, "user_id": user_id, "client_id": client_id, "email": email}
