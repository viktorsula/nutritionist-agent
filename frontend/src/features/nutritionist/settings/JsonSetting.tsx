import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../../auth/AuthProvider";
import { Button } from "../../../components/ui/Button";
import { readSetting, saveSetting } from "./settingsApi";

/** Универсальный JSON-редактор настройки system_settings по ключу. */
export function JsonSetting({ settingKey, hint }: { settingKey: string; hint?: string }) {
  const { t } = useTranslation();
  const { appUser } = useAuth();

  const query = useQuery({
    queryKey: ["setting", settingKey],
    queryFn: () => readSetting(settingKey),
  });

  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (query.data !== undefined) {
      setText(query.data === null ? "" : JSON.stringify(query.data, null, 2));
    }
  }, [query.data]);

  async function save() {
    setOk("");
    setError("");
    let parsed: unknown = null;
    const trimmed = text.trim();
    if (trimmed) {
      try {
        parsed = JSON.parse(trimmed);
      } catch (e) {
        setError(t("settings.json.invalid", { msg: e instanceof Error ? e.message : "" }));
        return;
      }
    }
    setBusy(true);
    try {
      await saveSetting(settingKey, parsed, appUser?.user_id);
      setOk(t("settings.json.saved"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.json.error"));
    } finally {
      setBusy(false);
    }
  }

  if (query.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;

  return (
    <div className="space-y-2">
      <textarea
        className="h-48 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={hint}
        spellCheck={false}
      />
      <div className="flex items-center gap-2">
        <Button type="button" onClick={save} disabled={busy}>
          {busy ? t("settings.json.saving") : t("settings.json.save")}
        </Button>
        {ok && <span className="text-xs text-green-600">{ok}</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    </div>
  );
}
