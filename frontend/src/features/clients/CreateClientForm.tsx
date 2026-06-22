import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/Button";

/** Форма создания/приглашения клиента (кабинет нутрициолога). */
export function CreateClientForm() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Dubai");
  const [language, setLanguage] = useState("ru");
  const [paid, setPaid] = useState(true); // оплачено / не оплачено
  const [mode, setMode] = useState<"basic" | "full">("full"); // базовый / полный
  const [paidUntil, setPaidUntil] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk("");
    setError("");
    // Дата окончания обязательна, если услуга оплачена.
    if (paid && !paidUntil) {
      setError(t("clients.paid_until_required"));
      return;
    }
    setBusy(true);
    try {
      await api.createClient({
        email,
        name,
        timezone,
        language,
        paid,
        mode,
        paid_until: paid ? paidUntil : null,
      });
      setOk(t("clients.created", { email }));
      setEmail("");
      setName("");
      setPaidUntil("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("clients.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-3 py-2 text-sm";
  const label = "mb-1 block text-xs font-medium text-gray-500";

  return (
    <form onSubmit={submit} className="max-w-md space-y-3">
      <h3 className="text-sm font-semibold text-gray-700">{t("clients.create_title")}</h3>
      <input
        type="email"
        required
        placeholder={t("clients.email")}
        className={input}
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        type="text"
        required
        placeholder={t("clients.name")}
        className={input}
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="flex gap-2">
        <input
          type="text"
          placeholder={t("clients.timezone")}
          className={input}
          value={timezone}
          onChange={(e) => setTimezone(e.target.value)}
        />
        <select
          className={input}
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
        >
          <option value="ru">RU</option>
          <option value="en">EN</option>
        </select>
      </div>

      {/* Стартовые статусы — задаёт нутрициолог, обязательны для входа клиента. */}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={label}>{t("clients.payment")}</label>
          <select
            className={input}
            value={paid ? "paid" : "unpaid"}
            onChange={(e) => setPaid(e.target.value === "paid")}
          >
            <option value="paid">{t("clients.paid")}</option>
            <option value="unpaid">{t("clients.unpaid")}</option>
          </select>
        </div>
        <div>
          <label className={label}>{t("clients.mode")}</label>
          <select
            className={input}
            value={mode}
            onChange={(e) => setMode(e.target.value as "basic" | "full")}
          >
            <option value="full">{t("clients.mode_full")}</option>
            <option value="basic">{t("clients.mode_basic")}</option>
          </select>
        </div>
      </div>

      {paid && (
        <div>
          <label className={label}>{t("clients.paid_until")}</label>
          <input
            type="date"
            required
            className={input}
            value={paidUntil}
            onChange={(e) => setPaidUntil(e.target.value)}
          />
        </div>
      )}

      {ok && <div className="text-sm text-green-600">{ok}</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}

      <Button type="submit" disabled={busy}>
        {busy ? t("clients.creating") : t("clients.create_button")}
      </Button>
    </form>
  );
}
