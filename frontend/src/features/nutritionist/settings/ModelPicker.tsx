import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import type { ModelRef } from "./llmConfigOps";

interface Props {
  value: ModelRef;
  /** Все известные провайдеры и подмножество доступных (ключ задан). */
  providers: { available: string[]; all: string[] };
  onChange: (ref: Partial<ModelRef>) => void;
}

/**
 * Выбор провайдера + модели: провайдер из выпадашки (недоступные помечены),
 * модель — поле с живым datalist (ListModels) + свободный ввод новинок. Кнопка
 * «Проверить» пингует выбранную модель перед сохранением.
 */
export function ModelPicker({ value, providers, onChange }: Props) {
  const { t } = useTranslation();
  const listId = useId();

  const modelsQuery = useQuery({
    queryKey: ["llmModels", value.provider],
    queryFn: () => api.llmModels(value.provider),
    enabled: Boolean(value.provider),
    staleTime: 5 * 60 * 1000,
  });
  const models = modelsQuery.data?.models ?? [];

  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  async function test() {
    setResult(null);
    if (!value.provider || !value.model.trim()) {
      setResult({ ok: false, text: t("settings.llm.test_need_model") });
      return;
    }
    setTesting(true);
    try {
      const r = await api.llmTest(value.provider, value.model.trim());
      setResult(
        r.ok
          ? { ok: true, text: t("settings.llm.test_ok", { ms: r.latency_ms }) }
          : { ok: false, text: r.error ?? t("settings.llm.test_fail") },
      );
    } catch (e) {
      setResult({ ok: false, text: e instanceof Error ? e.message : t("settings.llm.test_fail") });
    } finally {
      setTesting(false);
    }
  }

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border px-2 py-1 text-xs"
          value={value.provider}
          onChange={(e) => onChange({ provider: e.target.value })}
        >
          <option value="">{t("settings.llm.provider")}</option>
          {providers.all.map((p) => (
            <option key={p} value={p}>
              {p}
              {providers.available.includes(p) ? "" : ` ${t("settings.llm.no_key")}`}
            </option>
          ))}
        </select>

        <input
          className="min-w-[14rem] flex-1 rounded-md border px-2 py-1 font-mono text-xs"
          list={listId}
          value={value.model}
          placeholder={t("settings.llm.model")}
          spellCheck={false}
          onChange={(e) => onChange({ model: e.target.value })}
        />
        <datalist id={listId}>
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>

        <button
          type="button"
          className="rounded-md border border-brand px-2 py-1 text-xs text-brand hover:bg-brand-light disabled:opacity-50"
          onClick={test}
          disabled={testing}
        >
          {testing ? t("settings.llm.testing") : t("settings.llm.test")}
        </button>
      </div>
      {result && (
        <div className={`text-xs ${result.ok ? "text-green-600" : "text-red-600"}`}>{result.text}</div>
      )}
    </div>
  );
}
