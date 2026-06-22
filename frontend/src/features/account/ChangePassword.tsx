import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/ui/Button";

/** Кнопка «Сменить пароль» + модальное окно (смена пароля залогиненного пользователя). */
export function ChangePassword() {
  const { t } = useTranslation();
  const { changePassword } = useAuth();

  const [open, setOpen] = useState(false);
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  function close() {
    setOpen(false);
    setPw("");
    setPw2("");
    setMsg("");
    setError("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    if (pw.length < 6) {
      setError(t("account.too_short"));
      return;
    }
    if (pw !== pw2) {
      setError(t("account.mismatch"));
      return;
    }
    setBusy(true);
    try {
      await changePassword(pw);
      setMsg(t("account.saved"));
      setPw("");
      setPw2("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("account.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-3 py-2 text-sm";

  return (
    <>
      <Button variant="outline" onClick={() => setOpen(true)}>
        {t("nav.change_password")}
      </Button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
          onClick={close}
        >
          <div
            className="w-full max-w-sm rounded-xl bg-white p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-4 text-sm font-semibold text-brand-dark">
              {t("account.change_password_title")}
            </h3>
            <form onSubmit={submit} className="space-y-3">
              <input
                type="password"
                required
                placeholder={t("account.new_password")}
                className={input}
                value={pw}
                onChange={(e) => setPw(e.target.value)}
              />
              <input
                type="password"
                required
                placeholder={t("account.confirm_password")}
                className={input}
                value={pw2}
                onChange={(e) => setPw2(e.target.value)}
              />
              {msg && <div className="text-sm text-green-600">{msg}</div>}
              {error && <div className="text-sm text-red-600">{error}</div>}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" type="button" onClick={close} disabled={busy}>
                  {t("account.cancel")}
                </Button>
                <Button type="submit" disabled={busy}>
                  {busy ? t("account.saving") : t("account.save")}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
