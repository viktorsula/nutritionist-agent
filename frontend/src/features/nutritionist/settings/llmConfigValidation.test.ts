import { describe, it, expect } from "vitest";
import { validateLlmConfig } from "./llmConfigValidation";

describe("validateLlmConfig", () => {
  const valid = {
    dialog: {
      provider: "groq",
      model: "llama-3.3-70b-versatile",
      temperature: 0.7,
      max_tokens: 2000,
      fallbacks: [{ provider: "gemini", model: "gemini-2.5-flash" }],
    },
  };

  it("принимает корректный конфиг", () => {
    expect(validateLlmConfig(valid)).toEqual([]);
  });

  it("null (пусто) допустим — откат на код-дефолты", () => {
    expect(validateLlmConfig(null)).toEqual([]);
  });

  it("не-объект на верхнем уровне → ошибка root", () => {
    expect(validateLlmConfig([])).toHaveLength(1);
    expect(validateLlmConfig("x")).toHaveLength(1);
  });

  it("неизвестный провайдер → ошибка", () => {
    const cfg = { dialog: { provider: "openai", model: "gpt-4o" } };
    expect(validateLlmConfig(cfg)).toEqual([
      "dialog.provider: один из groq, claude, gemini",
    ]);
  });

  it("пустой/нестроковый model → ошибка", () => {
    expect(validateLlmConfig({ dialog: { provider: "groq", model: "" } })).toEqual([
      "dialog.model: непустая строка",
    ]);
    expect(validateLlmConfig({ dialog: { provider: "groq", model: 5 } })).toEqual([
      "dialog.model: непустая строка",
    ]);
  });

  it("fallbacks не массив → ошибка", () => {
    const cfg = { dialog: { provider: "groq", model: "m", fallbacks: {} } };
    expect(validateLlmConfig(cfg)).toEqual(["dialog.fallbacks: массив"]);
  });

  it("кривой элемент fallbacks → адресная ошибка", () => {
    const cfg = {
      dialog: { provider: "groq", model: "m", fallbacks: [{ provider: "nope", model: "" }] },
    };
    expect(validateLlmConfig(cfg)).toEqual([
      "dialog.fallbacks[0].provider: один из groq, claude, gemini",
      "dialog.fallbacks[0].model: непустая строка",
    ]);
  });

  it("задача-не-объект → ошибка", () => {
    expect(validateLlmConfig({ dialog: "groq" })).toEqual([
      "dialog: ожидается объект с provider/model",
    ]);
  });

  it("_providers + кастом-провайдер в задаче — допустимо", () => {
    const cfg = {
      _providers: { mistral: { base_url: "https://api.mistral.ai/v1", api_key_env: "MISTRAL_API_KEY" } },
      dialog: { provider: "mistral", model: "mistral-large-latest" },
    };
    expect(validateLlmConfig(cfg)).toEqual([]);
  });

  it("_providers не валидируется как задача (нет provider/model)", () => {
    const cfg = {
      _providers: { mistral: { base_url: "https://x/v1", api_key_env: "K" } },
      dialog: { provider: "groq", model: "m" },
    };
    const errs = validateLlmConfig(cfg);
    expect(errs.some((e) => e.startsWith("_providers:"))).toBe(false);
  });

  it("кривой _providers → адресная ошибка", () => {
    const cfg = { _providers: { mistral: { base_url: "" } } };
    expect(validateLlmConfig(cfg)).toEqual([
      "_providers.mistral.base_url: непустая строка",
      "_providers.mistral.api_key_env: непустая строка",
    ]);
  });

  it("неизвестный провайдер (нет в _providers) → ошибка", () => {
    const cfg = { dialog: { provider: "mistral", model: "m" } };
    expect(validateLlmConfig(cfg)).toEqual([
      "dialog.provider: один из groq, claude, gemini",
    ]);
  });
});

describe("validateLlmConfig — P0-4: orchestrator/nutritionist_orchestrator требуют tool-capable провайдера", () => {
  it("claude для orchestrator — допустимо", () => {
    const cfg = { orchestrator: { provider: "claude", model: "claude-sonnet-4-6" } };
    expect(validateLlmConfig(cfg)).toEqual([]);
  });

  it("не-claude провайдер для orchestrator → ошибка", () => {
    const cfg = { orchestrator: { provider: "groq", model: "llama-3.3-70b-versatile" } };
    expect(validateLlmConfig(cfg)).toEqual([
      "orchestrator.provider: должен быть одним из claude (инструменты работают только " +
        "там — другой провайдер молча теряет все инструменты записи данных клиента)",
    ]);
  });

  it("не-claude провайдер для nutritionist_orchestrator → ошибка", () => {
    const cfg = { nutritionist_orchestrator: { provider: "gemini", model: "gemini-2.5-flash" } };
    expect(validateLlmConfig(cfg).length).toBe(1);
  });

  it("не-claude в fallbacks orchestrator → адресная ошибка", () => {
    const cfg = {
      orchestrator: {
        provider: "claude",
        model: "claude-sonnet-4-6",
        fallbacks: [{ provider: "groq", model: "llama-3.3-70b-versatile" }],
      },
    };
    const errs = validateLlmConfig(cfg);
    expect(errs.some((e) => e.startsWith("orchestrator.fallbacks[0].provider:"))).toBe(true);
  });

  it("claude в fallbacks orchestrator — допустимо", () => {
    const cfg = {
      orchestrator: {
        provider: "claude",
        model: "claude-sonnet-4-6",
        fallbacks: [{ provider: "claude", model: "claude-haiku-4-5" }],
      },
    };
    expect(validateLlmConfig(cfg)).toEqual([]);
  });

  it("не-tool-задачи (dialog/analytics/...) — любой известный провайдер допустим", () => {
    const cfg = { dialog: { provider: "groq", model: "llama-3.3-70b-versatile" } };
    expect(validateLlmConfig(cfg)).toEqual([]);
  });
});
