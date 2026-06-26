import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api, type PromptMeta } from "../../../lib/api";
import { Button } from "../../../components/ui/Button";

/**
 * Редактор промптов. Список берётся из реестра (понятные названия + раздел):
 * - «Коммуникационные» — нутрициолог правит сам (сохранение в БД, приоритет над .md);
 * - «Системные» — read-only (правит разработчик в файлах), показываются для прозрачности.
 */
export function PromptEditor() {
  const { t, i18n } = useTranslation();

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

  const items = useMemo(() => list.data ?? [], [list.data]);
  const byKey = useMemo(() => new Map(items.map((p) => [p.key, p])), [items]);
  const communication = items.filter((p) => p.section === "communication");
  const system = items.filter((p) => p.section === "system");

  const label = (p: PromptMeta) => (i18n.language.startsWith("ru") ? p.label_ru : p.label_en);

  // Автовыбор первого промпта.
  useEffect(() => {
    if (!name && items.length) setName(items[0].key);
  }, [items, name]);

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
      list.refetch();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.prompts.save_error"));
    } finally {
      setBusy(false);
    }
  }

  if (list.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;
  if (list.error) return <div className="text-sm text-red-600">{t("settings.prompts.list_error")}</div>;

  const current = byKey.get(name);
  const readOnly = current ? !current.editable : false;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        >
          <optgroup label={t("settings.prompts.group_communication")}>
            {communication.map((p) => (
              <option key={p.key} value={p.key}>
                {label(p)}
              </option>
            ))}
          </optgroup>
          <optgroup label={t("settings.prompts.group_system")}>
            {system.map((p) => (
              <option key={p.key} value={p.key}>
                {label(p)}
              </option>
            ))}
          </optgroup>
        </select>
        {current && (
          <span className="text-xs text-gray-400">
            {t("settings.prompts.source")}: {current.source} · {current.llm}
          </span>
        )}
        {readOnly && (
          <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
            {t("settings.prompts.readonly_badge")}
          </span>
        )}
      </div>

      {readOnly && (
        <p className="text-xs text-amber-600">{t("settings.prompts.readonly_note")}</p>
      )}

      <textarea
        className="h-64 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs disabled:bg-gray-50 disabled:text-gray-500"
        value={loadingText ? t("loading") : text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        readOnly={readOnly}
        disabled={readOnly}
      />

      {!readOnly && (
        <>
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
        </>
      )}
      {readOnly && error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
