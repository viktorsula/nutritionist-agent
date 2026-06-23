import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/Button";

/**
 * Экран восстановления пароля. Показывается, когда пользователь перешёл по
 * ссылке из письма сброса (событие PASSWORD_RECOVERY) — сессия восстановления
 * уже установлена, остаётся задать новый пароль через updateUser.
 */
export function SetNewPassword() {
  const { t } = useTranslation();
  const { changePassword, endRecovery } = useAuth();
  const navigate = useNavigate();

  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (pw.length < 6) {
      setError(t("recovery.too_short"));
      return;
    }
    if (pw !== pw2) {
      setError(t("recovery.mismatch"));
      return;
    }
    setBusy(true);
    try {
      await changePassword(pw);
      endRecovery();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("recovery.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-3 py-2 text-sm";

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-light px-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow">
        <div className="mb-1 text-center text-2xl">🔑</div>
        <h1 className="mb-1 text-center text-lg font-semibold text-brand-dark">
          {t("recovery.title")}
        </h1>
        <p className="mb-6 text-center text-xs text-gray-500">{t("recovery.hint")}</p>

        <form onSubmit={submit} className="space-y-3">
          <input
            type="password"
            required
            placeholder={t("recovery.new_password")}
            className={input}
            value={pw}
            onChange={(e) => setPw(e.target.value)}
          />
          <input
            type="password"
            required
            placeholder={t("recovery.confirm_password")}
            className={input}
            value={pw2}
            onChange={(e) => setPw2(e.target.value)}
          />
          {error && <div className="text-sm text-red-600">{error}</div>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? t("recovery.saving") : t("recovery.save")}
          </Button>
        </form>
      </div>
    </div>
  );
}
