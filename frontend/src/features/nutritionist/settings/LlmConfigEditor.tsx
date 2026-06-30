import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../../lib/api";
import { Button } from "../../../components/ui/Button";
import { readSetting, saveSetting } from "./settingsApi";
import { validateLlmConfig } from "./llmConfigValidation";
import { ModelPicker } from "./ModelPicker";
import {
  TASK_ORDER,
  setPrimary,
  setParam,
  addFallback,
  removeFallback,
  updateFallback,
  moveFallback,
  resetTask,
  type LlmConfig,
} from "./llmConfigOps";

type Providers = { available: string[]; all: string[] };

/** Одна карточка задачи: основная модель + резерв + параметры + сброс. */
function TaskCard({
  task,
  cfg,
  defaults,
  providers,
  setCfg,
}: {
  task: string;
  cfg: LlmConfig;
  defaults: LlmConfig;
  providers: Providers;
  setCfg: (next: LlmConfig) => void;
}) {
  const { t } = useTranslation();
  const entry = cfg[task] ?? { provider: "", model: "" };
  const fallbacks = entry.fallbacks ?? [];

  return (
    <div className="rounded-md border bg-white p-3">
      <div className="mb-1 flex items-center justify-between">
        <div>
          <div className="text-sm font-semibold text-brand-dark">{t(`settings.llm.tasks.${task}.title`)}</div>
          <div className="text-xs text-gray-500">{t(`settings.llm.tasks.${task}.desc`)}</div>
        </div>
        <button
          type="button"
          className="text-xs text-gray-500 underline hover:text-brand"
          onClick={() => setCfg(resetTask(cfg, task, defaults))}
          disabled={!defaults[task]}
        >
          {t("settings.llm.reset")}
        </button>
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-medium text-gray-600">{t("settings.llm.primary")}</div>
        <ModelPicker
          value={{ provider: entry.provider, model: entry.model }}
          providers={providers}
          onChange={(ref) => setCfg(setPrimary(cfg, task, ref))}
        />
      </div>

      <div className="mb-2">
        <div className="mb-1 text-xs font-medium text-gray-600">{t("settings.llm.fallbacks")}</div>
        {fallbacks.length === 0 && <div className="text-xs text-gray-400">{t("settings.llm.no_fallbacks")}</div>}
        <div className="space-y-1">
          {fallbacks.map((fb, i) => (
            <div key={i} className="flex items-start gap-1">
              <div className="flex-1">
                <ModelPicker
                  value={fb}
                  providers={providers}
                  onChange={(ref) => setCfg(updateFallback(cfg, task, i, ref))}
                />
              </div>
              <button
                type="button"
                className="px-1 text-xs text-gray-400 hover:text-brand disabled:opacity-30"
                onClick={() => setCfg(moveFallback(cfg, task, i, -1))}
                disabled={i === 0}
                title={t("settings.llm.move_up")}
              >
                ↑
              </button>
              <button
                type="button"
                className="px-1 text-xs text-gray-400 hover:text-brand disabled:opacity-30"
                onClick={() => setCfg(moveFallback(cfg, task, i, 1))}
                disabled={i === fallbacks.length - 1}
                title={t("settings.llm.move_down")}
              >
                ↓
              </button>
              <button
                type="button"
                className="px-1 text-xs text-red-400 hover:text-red-600"
                onClick={() => setCfg(removeFallback(cfg, task, i))}
                title={t("settings.llm.remove")}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          className="mt-1 text-xs text-brand underline"
          onClick={() => setCfg(addFallback(cfg, task, { provider: entry.provider, model: "" }))}
        >
          + {t("settings.llm.add_fallback")}
        </button>
      </div>

      <details className="text-xs">
        <summary className="cursor-pointer text-gray-500">{t("settings.llm.advanced")}</summary>
        <div className="mt-1 flex flex-wrap gap-3">
          <label className="flex items-center gap-1">
            temperature
            <input
              type="number"
              step="0.1"
              min="0"
              max="2"
              className="w-20 rounded-md border px-2 py-1"
              value={entry.temperature ?? ""}
              onChange={(e) =>
                setCfg(setParam(cfg, task, "temperature", e.target.value === "" ? undefined : Number(e.target.value)))
              }
            />
          </label>
          <label className="flex items-center gap-1">
            max_tokens
            <input
              type="number"
              step="100"
              min="1"
              className="w-24 rounded-md border px-2 py-1"
              value={entry.max_tokens ?? ""}
              onChange={(e) =>
                setCfg(setParam(cfg, task, "max_tokens", e.target.value === "" ? undefined : Number(e.target.value)))
              }
            />
          </label>
        </div>
      </details>
    </div>
  );
}

/**
 * Окно «LLM-модели» — порт смены инструмента без кода: по каждой задаче основная
 * модель + резерв (живой список ListModels + ручной ввод), кнопка «Проверить»,
 * сброс на дефолт. Экспертный режим — сырой JSON. Источник — system_settings.llm_config.
 */
export function LlmConfigEditor() {
  const { t } = useTranslation();

  const cfgQuery = useQuery({ queryKey: ["setting", "llm_config"], queryFn: () => readSetting("llm_config") });
  const providersQuery = useQuery({ queryKey: ["llmProviders"], queryFn: () => api.llmProviders() });
  const defaultsQuery = useQuery({ queryKey: ["llmDefaults"], queryFn: () => api.llmDefaults() });

  const [cfg, setCfg] = useState<LlmConfig>({});
  const [expert, setExpert] = useState(false);
  const [selectedTask, setSelectedTask] = useState<string>("");
  const [rawText, setRawText] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");
  const [issues, setIssues] = useState<string[]>([]);

  useEffect(() => {
    if (cfgQuery.data !== undefined) {
      const value = (cfgQuery.data === null ? {} : cfgQuery.data) as LlmConfig;
      setCfg(value);
      setRawText(cfgQuery.data === null ? "" : JSON.stringify(cfgQuery.data, null, 2));
    }
  }, [cfgQuery.data]);

  const providers: Providers = providersQuery.data ?? { available: [], all: ["groq", "claude", "gemini"] };
  const defaults = (defaultsQuery.data ?? {}) as LlmConfig;

  async function save() {
    setOk("");
    setError("");
    setIssues([]);

    // В экспертном режиме источник правды — текст; иначе — структурный cfg.
    let value: unknown = cfg;
    if (expert) {
      const trimmed = rawText.trim();
      if (!trimmed) {
        value = null;
      } else {
        try {
          value = JSON.parse(trimmed);
        } catch (e) {
          setError(t("settings.json.invalid", { msg: e instanceof Error ? e.message : "" }));
          return;
        }
      }
    }

    const problems = validateLlmConfig(value);
    if (problems.length) {
      setIssues(problems);
      return;
    }

    setBusy(true);
    try {
      await saveSetting("llm_config", value);
      setOk(t("settings.json.saved"));
      if (!expert) setRawText(JSON.stringify(value, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.json.error"));
    } finally {
      setBusy(false);
    }
  }

  if (cfgQuery.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">{t("settings.llm.structure")}</p>
        <button
          type="button"
          className="text-xs text-gray-500 underline hover:text-brand"
          onClick={() => {
            if (!expert) {
              setRawText(JSON.stringify(cfg, null, 2));
              setExpert(true);
            } else {
              // эксперт → обычный: переносим правки из JSON в карточки, если валидный объект
              try {
                const parsed = JSON.parse(rawText.trim() || "{}");
                if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
                  setCfg(parsed as LlmConfig);
                }
              } catch {
                /* не парсится — оставляем карточки как есть */
              }
              setExpert(false);
            }
          }}
        >
          {expert ? t("settings.llm.mode_structured") : t("settings.llm.mode_expert")}
        </button>
      </div>

      <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        {t("settings.llm.code_note")}
      </div>

      {expert ? (
        <>
          <textarea
            className="h-72 w-full resize-y rounded-md border px-3 py-2 font-mono text-xs"
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            spellCheck={false}
          />
          <p className="text-xs text-gray-400">{t("settings.llm.empty_note")}</p>
        </>
      ) : (
        (() => {
          const tasks = TASK_ORDER.filter((task) => cfg[task]);
          const current = selectedTask && tasks.includes(selectedTask) ? selectedTask : (tasks[0] ?? "");
          return (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-xs text-gray-600">
                {t("settings.llm.choose_task")}
                <select
                  className="rounded-md border px-2 py-1 text-xs"
                  value={current}
                  onChange={(e) => setSelectedTask(e.target.value)}
                >
                  {tasks.map((task) => (
                    <option key={task} value={task}>
                      {t(`settings.llm.tasks.${task}.title`)}
                    </option>
                  ))}
                </select>
              </label>
              {current && cfg[current] && (
                <TaskCard task={current} cfg={cfg} defaults={defaults} providers={providers} setCfg={setCfg} />
              )}
            </div>
          );
        })()
      )}

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
