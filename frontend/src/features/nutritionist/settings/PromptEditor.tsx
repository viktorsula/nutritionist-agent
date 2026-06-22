import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { Button } from "../../../components/ui/Button";

/** Редактор промптов: список (файлы+БД) → загрузка текста → сохранение в БД (приоритет над файлом). */
export function PromptEditor() {
  const { t } = useTranslation();

  const list = useQuery({
    queryKey: ["prompts_list"],
    queryFn: () => api.promptsList(),
  });

  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [description, setDescription] = useState("");
  const [loadingText, setLoadingText] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  const names = Object.keys(list.data ?? {}).sort();

  // Автовыбор первого промпта.
  useEffect(() => {
    if (!name && names.length) setName(names[0]);
  }, [names, name]);

  // Загрузка текста выбранного промпта.
  useEffect(() => {
    if (!name) return;
    setLoadingText(true);
    setOk("");
    setError("");
    api
      .promptLoad(name)
      .then((r) => setText(r.text))
      .catch((e) => setError(e instanceof Error ? e.message : t("settings.prompts.load_error")))
      .finally(() => setLoadingText(false));
  }, [name, t]);

  async function save() {
    setOk("");
    setError("");
    setBusy(true);
    try {
      await api.promptSave({ name, text, description: description || undefined });
      setOk(t("settings.prompts.saved"));
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.prompts.save_error"));
    } finally {
      setBusy(false);
    }
  }

  if (list.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;
  if (list.error) return <div className="text-sm text-red-600">{t("settings.prompts.list_error")}</div>;

  const source = (list.data ?? {})[name]?.source;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <select
          className="rounded-md border px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        >
          {names.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
        {source && (
          <span className="text-xs text-gray-400">
            {t("settings.prompts.source")}: {source}
          </span>
        )}
      </div>

      <textarea
        className="h-64 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs"
        value={loadingText ? t("loading") : text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
      />
      <input
        className="w-full rounded-md border px-3 py-2 text-sm"
        placeholder={t("settings.prompts.description")}
        value={description}
        onChange={(e) => setDescription(e.target.value)}
      />
      <div className="flex items-center gap-2">
        <Button type="button" onClick={save} disabled={busy || loadingText}>
          {busy ? t("settings.prompts.saving") : t("settings.prompts.save")}
        </Button>
        {ok && <span className="text-xs text-green-600">{ok}</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    </div>
  );
}
