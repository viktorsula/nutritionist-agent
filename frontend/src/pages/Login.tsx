import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/Button";

type Mode = "password" | "otp_request" | "otp_verify";

export function Login() {
  const { t, i18n } = useTranslation();
  const { signInWithPassword, sendOtp, verifyOtp, resetPassword } = useAuth();

  const [mode, setMode] = useState<Mode>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent) {
    e.preventDefault();
    setError("");
    setInfo("");
    setBusy(true);
    try {
      if (mode === "password") {
        await signInWithPassword(email, password);
      } else if (mode === "otp_request") {
        await sendOtp(email);
        setMode("otp_verify");
      } else {
        await verifyOtp(email, code);
      }
    } catch {
      setError(t("login.error"));
    } finally {
      setBusy(false);
    }
  }

  async function handleForgot() {
    setError("");
    setInfo("");
    if (!email) {
      setError(t("login.email_required"));
      return;
    }
    setBusy(true);
    try {
      await resetPassword(email);
      setInfo(t("login.reset_sent"));
    } catch {
      setError(t("login.reset_error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-light px-4">
      <div className="w-full max-w-sm rounded-xl bg-white p-8 shadow">
        <div className="mb-1 text-center text-2xl">🥗</div>
        <h1 className="mb-1 text-center text-lg font-semibold text-brand-dark">
          {t("app_title")}
        </h1>
        <p className="mb-6 text-center text-xs text-gray-500">{t("welcome_brand")}</p>

        <form onSubmit={handle} className="space-y-3">
          <input
            type="email"
            required
            placeholder={t("login.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-md border px-3 py-2 text-sm"
          />

          {mode === "password" && (
            <input
              type="password"
              required
              placeholder={t("login.password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          )}

          {mode === "otp_verify" && (
            <input
              type="text"
              required
              placeholder={t("login.code")}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="w-full rounded-md border px-3 py-2 text-sm"
            />
          )}

          {error && <div className="text-sm text-red-600">{error}</div>}
          {info && <div className="text-sm text-green-600">{info}</div>}

          <Button type="submit" disabled={busy} className="w-full">
            {mode === "password" && t("login.sign_in")}
            {mode === "otp_request" && t("login.send_code")}
            {mode === "otp_verify" && t("login.verify")}
          </Button>
        </form>

        <div className="mt-4 flex flex-col items-center gap-2">
          {mode === "password" ? (
            <>
              <button
                type="button"
                onClick={handleForgot}
                disabled={busy}
                className="text-xs text-brand hover:underline disabled:opacity-50"
              >
                {t("login.forgot")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setError("");
                  setInfo("");
                  setMode("otp_request");
                }}
                className="text-xs text-brand hover:underline"
              >
                {t("login.use_code")}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={() => {
                setError("");
                setInfo("");
                setMode("password");
              }}
              className="text-xs text-brand hover:underline"
            >
              {t("login.use_password")}
            </button>
          )}
        </div>

        <div className="mt-4 flex justify-center gap-2 text-xs text-gray-400">
          {["ru", "en"].map((lng) => (
            <button
              key={lng}
              onClick={() => {
                i18n.changeLanguage(lng);
                localStorage.setItem("lang", lng);
              }}
              className={i18n.resolvedLanguage === lng ? "font-semibold text-brand" : ""}
            >
              {lng.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
