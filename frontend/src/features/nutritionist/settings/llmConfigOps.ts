/**
 * Чистые иммутабельные операции над llm_config (без React) — чтобы логику окна
 * «LLM-модели» можно было протестировать отдельно от UI.
 */

export interface ModelRef {
  provider: string;
  model: string;
}

export interface TaskConfig {
  provider: string;
  model: string;
  temperature?: number;
  max_tokens?: number;
  fallbacks?: ModelRef[];
}

export type LlmConfig = Record<string, TaskConfig>;

/** Порядок и человекочитаемые ключи задач (для подписей берётся из i18n по этому ключу). */
export const TASK_ORDER = [
  "dialog",
  "vision",
  "nutrition_analysis",
  "analytics",
  "summary",
  "planning",
];

function cloneTask(t: TaskConfig): TaskConfig {
  return { ...t, fallbacks: (t.fallbacks ?? []).map((f) => ({ ...f })) };
}

function withTask(cfg: LlmConfig, task: string, next: TaskConfig): LlmConfig {
  return { ...cfg, [task]: next };
}

/** Меняет провайдера/модель основной модели задачи. */
export function setPrimary(cfg: LlmConfig, task: string, ref: Partial<ModelRef>): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  if (ref.provider !== undefined) t.provider = ref.provider;
  if (ref.model !== undefined) t.model = ref.model;
  return withTask(cfg, task, t);
}

/** Устанавливает числовой параметр (temperature/max_tokens); undefined — удаляет ключ. */
export function setParam(
  cfg: LlmConfig,
  task: string,
  key: "temperature" | "max_tokens",
  value: number | undefined,
): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  if (value === undefined || Number.isNaN(value)) delete t[key];
  else t[key] = value;
  return withTask(cfg, task, t);
}

/** Добавляет резервную модель в конец цепочки. */
export function addFallback(cfg: LlmConfig, task: string, ref: ModelRef): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  t.fallbacks = [...(t.fallbacks ?? []), { ...ref }];
  return withTask(cfg, task, t);
}

/** Удаляет резерв по индексу. */
export function removeFallback(cfg: LlmConfig, task: string, idx: number): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  t.fallbacks = (t.fallbacks ?? []).filter((_, i) => i !== idx);
  return withTask(cfg, task, t);
}

/** Меняет провайдера/модель резерва по индексу. */
export function updateFallback(
  cfg: LlmConfig,
  task: string,
  idx: number,
  ref: Partial<ModelRef>,
): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  const list = t.fallbacks ?? [];
  if (idx < 0 || idx >= list.length) return cfg;
  list[idx] = { ...list[idx], ...ref };
  t.fallbacks = list;
  return withTask(cfg, task, t);
}

/** Переставляет резерв вверх (-1) или вниз (+1) — порядок = очередь перебора. */
export function moveFallback(cfg: LlmConfig, task: string, idx: number, dir: -1 | 1): LlmConfig {
  const t = cloneTask(cfg[task] ?? { provider: "", model: "" });
  const list = t.fallbacks ?? [];
  const j = idx + dir;
  if (idx < 0 || idx >= list.length || j < 0 || j >= list.length) return cfg;
  [list[idx], list[j]] = [list[j], list[idx]];
  t.fallbacks = list;
  return withTask(cfg, task, t);
}

/** Возвращает задачу к код-дефолту (из /nutritionist/llm/defaults). */
export function resetTask(cfg: LlmConfig, task: string, defaults: LlmConfig): LlmConfig {
  if (!defaults[task]) return cfg;
  return withTask(cfg, task, cloneTask(defaults[task]));
}
