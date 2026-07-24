/** Нативные провайдеры (свой SDK-адаптер). Кастом — из секции `_providers`. */
export const KNOWN_PROVIDERS = ["groq", "claude", "gemini"];

/**
 * Провайдеры с реализованным циклом tool-calling (см. utils/llm.py::TOOL_CAPABLE_PROVIDERS
 * — то же множество, зеркалим на фронте для мгновенной обратной связи в редакторе).
 * Не бренд-привязка: это ровно те провайдеры, чей адаптер умеет цикл tool_use →
 * выполнение → tool_result. Расширяется, когда появится такой же цикл для другого
 * провайдера (P2-22 в diagnostic_report.md).
 */
export const TOOL_CAPABLE_PROVIDERS = ["claude"];

/** Задачи с tool-calling — их провайдер обязан быть из TOOL_CAPABLE_PROVIDERS. */
export const TOOL_REQUIRED_TASKS = ["orchestrator", "nutritionist_orchestrator"];

/**
 * Структурная валидация llm_config (поверх JSON.parse). Возвращает список ошибок
 * (пустой = ок). Пустое значение (null) допустимо — откат на код-дефолты.
 *
 * Поддерживает реестр кастом-провайдеров `_providers` (OpenAI-совместимые):
 *   "_providers": { "<name>": { "base_url": str, "api_key_env": str } }
 * Имена из реестра становятся допустимыми provider у задач/резерва.
 */
export function validateLlmConfig(parsed: unknown): string[] {
  const errors: string[] = [];
  if (parsed === null) return errors;
  if (typeof parsed !== "object" || Array.isArray(parsed)) {
    return ["root: ожидается объект { task_type: {...} }"];
  }
  const obj = parsed as Record<string, unknown>;

  // ── Реестр кастом-провайдеров (необязателен) ───────────────────────────────
  const customNames: string[] = [];
  if (obj._providers !== undefined) {
    const reg = obj._providers;
    if (typeof reg !== "object" || reg === null || Array.isArray(reg)) {
      errors.push("_providers: объект { имя: { base_url, api_key_env } }");
    } else {
      for (const [name, raw] of Object.entries(reg as Record<string, unknown>)) {
        if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
          errors.push(`_providers.${name}: объект { base_url, api_key_env }`);
          continue;
        }
        const p = raw as Record<string, unknown>;
        if (typeof p.base_url !== "string" || !p.base_url.trim())
          errors.push(`_providers.${name}.base_url: непустая строка`);
        if (typeof p.api_key_env !== "string" || !p.api_key_env.trim())
          errors.push(`_providers.${name}.api_key_env: непустая строка`);
        customNames.push(name);
      }
    }
  }

  const allowed = [...KNOWN_PROVIDERS, ...customNames];
  const checkProvider = (where: string, p: unknown) => {
    if (typeof p !== "string" || !allowed.includes(p)) {
      errors.push(`${where}.provider: один из ${allowed.join(", ")}`);
    }
  };
  const checkModel = (where: string, m: unknown) => {
    if (typeof m !== "string" || !m.trim()) errors.push(`${where}.model: непустая строка`);
  };

  // ── Задачи (всё, кроме реестра) ────────────────────────────────────────────
  for (const [task, raw] of Object.entries(obj)) {
    if (task === "_providers") continue;
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      errors.push(`${task}: ожидается объект с provider/model`);
      continue;
    }
    const entry = raw as Record<string, unknown>;
    checkProvider(task, entry.provider);
    checkModel(task, entry.model);

    const toolRequired = TOOL_REQUIRED_TASKS.includes(task);
    const checkToolCapable = (where: string, p: unknown) => {
      if (toolRequired && typeof p === "string" && !TOOL_CAPABLE_PROVIDERS.includes(p)) {
        errors.push(
          `${where}.provider: должен быть одним из ${TOOL_CAPABLE_PROVIDERS.join(", ")} ` +
            `(инструменты работают только там — другой провайдер молча теряет все ` +
            `инструменты записи данных клиента)`,
        );
      }
    };
    checkToolCapable(task, entry.provider);

    if (entry.fallbacks !== undefined) {
      if (!Array.isArray(entry.fallbacks)) {
        errors.push(`${task}.fallbacks: массив`);
      } else {
        entry.fallbacks.forEach((fb, i) => {
          if (typeof fb !== "object" || fb === null || Array.isArray(fb)) {
            errors.push(`${task}.fallbacks[${i}]: объект { provider, model }`);
            return;
          }
          const f = fb as Record<string, unknown>;
          checkProvider(`${task}.fallbacks[${i}]`, f.provider);
          checkModel(`${task}.fallbacks[${i}]`, f.model);
          checkToolCapable(`${task}.fallbacks[${i}]`, f.provider);
        });
      }
    }
  }
  return errors;
}
