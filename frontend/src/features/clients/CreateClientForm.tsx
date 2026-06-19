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
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk("");
    setError("");
    setBusy(true);
    try {
      await api.createClient({ email, name, timezone, language });
      setOk(t("clients.created", { email }));
      setEmail("");
      setName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("clients.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-3 py-2 text-sm";

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

      {ok && <div className="text-sm text-green-600">{ok}</div>}
      {error && <div className="text-sm text-red-600">{error}</div>}

      <Button type="submit" disabled={busy}>
        {busy ? t("clients.creating") : t("clients.create_button")}
      </Button>
    </form>
  );
}
