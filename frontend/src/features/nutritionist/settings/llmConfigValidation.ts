/** Провайдеры, которые умеет utils/llm.call_llm (groq/claude/gemini). */
export const KNOWN_PROVIDERS = ["groq", "claude", "gemini"];

/**
 * Структурная валидация llm_config (поверх JSON.parse). Возвращает список ошибок
 * (пустой = ок). Защищает от валидного JSON с неверной структурой (опечатка в
 * provider, model не строка, кривой fallbacks) — иначе задача молча уйдёт в резерв
 * или код-дефолт. Пустое значение (null) допустимо — откат на код-дефолты.
 */
export function validateLlmConfig(parsed: unknown): string[] {
  const errors: string[] = [];
  if (parsed === null) return errors;
  if (typeof parsed !== "object" || Array.isArray(parsed)) {
    return ["root: ожидается объект { task_type: {...} }"];
  }

  const checkProvider = (where: string, p: unknown) => {
    if (typeof p !== "string" || !KNOWN_PROVIDERS.includes(p)) {
      errors.push(`${where}.provider: один из ${KNOWN_PROVIDERS.join(", ")}`);
    }
  };
  const checkModel = (where: string, m: unknown) => {
    if (typeof m !== "string" || !m.trim()) errors.push(`${where}.model: непустая строка`);
  };

  for (const [task, raw] of Object.entries(parsed as Record<string, unknown>)) {
    if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
      errors.push(`${task}: ожидается объект с provider/model`);
      continue;
    }
    const entry = raw as Record<string, unknown>;
    checkProvider(task, entry.provider);
    checkModel(task, entry.model);

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
        });
      }
    }
  }
  return errors;
}
