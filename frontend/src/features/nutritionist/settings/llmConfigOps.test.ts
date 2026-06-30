import { describe, it, expect } from "vitest";
import {
  setPrimary,
  setParam,
  addFallback,
  removeFallback,
  updateFallback,
  moveFallback,
  resetTask,
  type LlmConfig,
} from "./llmConfigOps";

const base: LlmConfig = {
  dialog: {
    provider: "groq",
    model: "llama-3.3-70b-versatile",
    temperature: 0.7,
    fallbacks: [{ provider: "gemini", model: "gemini-2.5-flash" }],
  },
};

describe("llmConfigOps (иммутабельность + операции)", () => {
  it("setPrimary не мутирует исходный объект", () => {
    const next = setPrimary(base, "dialog", { provider: "claude", model: "claude-sonnet-4-6" });
    expect(next.dialog.provider).toBe("claude");
    expect(next.dialog.model).toBe("claude-sonnet-4-6");
    expect(base.dialog.provider).toBe("groq"); // исходник цел
  });

  it("setParam удаляет ключ при undefined", () => {
    const next = setParam(base, "dialog", "temperature", undefined);
    expect("temperature" in next.dialog).toBe(false);
    expect(base.dialog.temperature).toBe(0.7);
  });

  it("addFallback добавляет в конец", () => {
    const next = addFallback(base, "dialog", { provider: "claude", model: "x" });
    expect(next.dialog.fallbacks).toEqual([
      { provider: "gemini", model: "gemini-2.5-flash" },
      { provider: "claude", model: "x" },
    ]);
    expect(base.dialog.fallbacks).toHaveLength(1);
  });

  it("removeFallback удаляет по индексу", () => {
    const next = removeFallback(base, "dialog", 0);
    expect(next.dialog.fallbacks).toEqual([]);
  });

  it("updateFallback меняет элемент; вне диапазона — без изменений", () => {
    const next = updateFallback(base, "dialog", 0, { model: "gemini-3.5-flash" });
    expect(next.dialog.fallbacks?.[0].model).toBe("gemini-3.5-flash");
    expect(updateFallback(base, "dialog", 9, { model: "z" })).toBe(base);
  });

  it("moveFallback переставляет; за границей — без изменений", () => {
    const two = addFallback(base, "dialog", { provider: "claude", model: "x" });
    const moved = moveFallback(two, "dialog", 0, 1);
    expect(moved.dialog.fallbacks?.map((f) => f.model)).toEqual(["x", "gemini-2.5-flash"]);
    expect(moveFallback(base, "dialog", 0, -1)).toBe(base); // некуда вверх
  });

  it("resetTask возвращает задачу к дефолту (копией)", () => {
    const defaults: LlmConfig = { dialog: { provider: "groq", model: "default-model" } };
    const edited = setPrimary(base, "dialog", { model: "changed" });
    const reset = resetTask(edited, "dialog", defaults);
    expect(reset.dialog.model).toBe("default-model");
    reset.dialog.model = "mutate";
    expect(defaults.dialog.model).toBe("default-model"); // дефолт не задет (копия)
  });
});
