import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../../auth/AuthProvider";
import { Button } from "../../../components/ui/Button";
import { readSetting, saveSetting } from "./settingsApi";
import { validateLlmConfig } from "./llmConfigValidation";

/**
 * Редактор llm_config: основная модель + резерв (fallbacks) по task_type.
 * JSON-редактор со структурной валидацией и подсказками (дропдауны моделей — позже).
 * Источник — system_settings.llm_config (после миграции 011); запись через бэкенд (audit).
 */
export function LlmConfigEditor() {
  const { t } = useTranslation();
  const { appUser } = useAuth();

  const query = useQuery({
    queryKey: ["setting", "llm_config"],
    queryFn: () => readSetting("llm_config"),
  });

  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<string[]>([]);

  useEffect(() => {
    if (query.data !== undefined) {
      setText(query.data === null ? "" : JSON.stringify(query.data, null, 2));
    }
  }, [query.data]);

  async function save() {
    setOk("");
    setError("");
    setIssues([]);

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

    const problems = validateLlmConfig(parsed);
    if (problems.length) {
      setIssues(problems);
      return;
    }

    setBusy(true);
    try {
      await saveSetting("llm_config", parsed, appUser?.user_id);
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
      <p className="text-xs text-gray-500">{t("settings.llm.structure")}</p>
      <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        {t("settings.llm.code_note")}
      </div>
      <textarea
        className="h-64 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs"
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
      />
      <p className="text-xs text-gray-400">{t("settings.llm.empty_note")}</p>
      {issues.length > 0 && (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
          <div className="mb-1 font-semibold">{t("settings.llm.invalid_config")}</div>
          <ul className="list-disc space-y-0.5 pl-4">
            {issues.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}
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
