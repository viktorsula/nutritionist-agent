import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthProvider";
import type { Role } from "../types";

interface Props {
  allow: Role[];
  children: ReactNode;
}

/**
 * Гейт маршрута: требует сессию + нужную роль. Для клиента дополнительно
 * проверяет доступ (frozen/inactive → экран «Доступ ограничен»).
 */
export function ProtectedRoute({ allow, children }: Props) {
  const { t } = useTranslation();
  const { session, appUser, loading } = useAuth();

  if (loading) {
    return <div className="p-8 text-gray-500">{t("loading")}</div>;
  }

  if (!session || !appUser) {
    return <Navigate to="/login" replace />;
  }

  if (!allow.includes(appUser.role)) {
    // Роль не подходит — отправляем на «свою» стартовую страницу.
    return <Navigate to={`/${appUser.role}`} replace />;
  }

  // Gate доступа для клиента — через бизнес-правило (оплата/заморозка/архив),
  // результат приходит из /me (web_allowed). Онбординг при этом разрешён.
  if (appUser.role === "client" && appUser.web_allowed === false) {
    return <Navigate to="/access-restricted" replace />;
  }

  return <>{children}</>;
}
