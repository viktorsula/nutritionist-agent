import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api, type PromptMeta } from "../../../lib/api";
import { Button } from "../../../components/ui/Button";

type Section = "communication" | "system";

/**
 * Редактор промптов — две вкладки:
 * - «Коммуникационные» — влияют на общение с клиентом и работу нутрициолога;
 * - «Системные» — технические (классификаторы/парсеры/vision); правка возможна,
 *   но с предупреждением (хрупкие форматы).
 * На каждой вкладке: выбор промпта + поле редактора + сохранение (БД-override над .md).
 */
export function PromptEditor() {
  const { t, i18n } = useTranslation();

  const list = useQuery({
    queryKey: ["prompts_list"],
    queryFn: () => api.promptsList(),
  });

  const [tab, setTab] = useState<Section>("communication");
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [description, setDescription] = useState("");
  const [loadingText, setLoadingText] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  const items = useMemo(() => list.data ?? [], [list.data]);
  const byKey = useMemo(() => new Map(items.map((p) => [p.key, p])), [items]);
  const inTab = useMemo(() => items.filter((p) => p.section === tab), [items, tab]);

  const label = (p: PromptMeta) => (i18n.language.startsWith("ru") ? p.label_ru : p.label_en);

  // Если выбранный промпт не из активной вкладки (или ничего не выбрано) — выбрать первый.
  useEffect(() => {
    if (!inTab.length) return;
    if (!inTab.some((p) => p.key === name)) setName(inTab[0].key);
  }, [inTab, name]);

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

  function switchTab(next: Section) {
    if (next === tab) return;
    setTab(next);
    setOk("");
    setError("");
    setDescription("");
  }

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
  const tabs: { key: Section; label: string }[] = [
    { key: "communication", label: t("settings.prompts.group_communication") },
    { key: "system", label: t("settings.prompts.group_system") },
  ];

  return (
    <div className="space-y-3">
      {/* Вкладки */}
      <div className="flex gap-1 border-b">
        {tabs.map((tb) => (
          <button
            key={tb.key}
            type="button"
            onClick={() => switchTab(tb.key)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${
              tab === tb.key
                ? "border-brand font-semibold text-brand-dark"
                : "border-transparent text-gray-500 hover:text-brand-dark"
            }`}
          >
            {tb.label}
          </button>
        ))}
      </div>

      {tab === "system" && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-700">
          {t("settings.prompts.system_warning")}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border px-2 py-1 text-sm"
          value={name}
          onChange={(e) => setName(e.target.value)}
        >
          {inTab.map((p) => (
            <option key={p.key} value={p.key}>
              {label(p)}
            </option>
          ))}
        </select>
        {current && (
          <span className="text-xs text-gray-400">
            {t("settings.prompts.source")}: {current.source} · {current.llm}
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
