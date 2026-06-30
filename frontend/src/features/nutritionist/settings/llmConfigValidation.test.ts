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
});
