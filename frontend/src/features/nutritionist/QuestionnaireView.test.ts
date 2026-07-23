import { describe, it, expect } from "vitest";
import { formatValue } from "./QuestionnaireView";
import type { Field } from "../questionnaire/schema";

const textField: Field = { id: "medications", type: "textarea", label: { ru: "Препараты", en: "Meds" } };
const numberField: Field = { id: "water_liters", type: "number", label: { ru: "Вода", en: "Water" }, unit: "л" };
const yesnoField: Field = { id: "smoking", type: "yesno_text", label: { ru: "Курение", en: "Smoking" } };
const selectField: Field = {
  id: "eating_out",
  type: "select",
  label: { ru: "Питание", en: "Eating" },
  options: [
    { value: "home", label: { ru: "Дома", en: "Home" } },
    { value: "out", label: { ru: "Вне дома", en: "Out" } },
  ],
};
const multiField: Field = {
  id: "improve_targets",
  type: "multiselect",
  label: { ru: "Улучшить", en: "Improve" },
  options: [
    { value: "health", label: { ru: "Здоровье", en: "Health" } },
    { value: "weight", label: { ru: "Вес", en: "Weight" } },
  ],
};
const fileField: Field = { id: "labs_files", type: "file", label: { ru: "Файлы", en: "Files" } };

describe("QuestionnaireView formatValue", () => {
  it("returns null for empty/undefined values", () => {
    expect(formatValue(textField, null, "ru")).toBeNull();
    expect(formatValue(textField, undefined, "ru")).toBeNull();
    expect(formatValue(textField, "", "ru")).toBeNull();
  });

  it("plain text passes through", () => {
    expect(formatValue(textField, "витамин D", "ru")).toBe("витамин D");
  });

  it("number field appends unit", () => {
    expect(formatValue(numberField, 1.5, "ru")).toBe("1.5 л");
  });

  it("file field is always hidden", () => {
    expect(formatValue(fileField, "some.pdf", "ru")).toBeNull();
  });

  it("yesno_text: no → 'нет'", () => {
    expect(formatValue(yesnoField, { answer: false, details: "" }, "ru")).toBe("нет");
  });

  it("yesno_text: yes with details", () => {
    expect(formatValue(yesnoField, { answer: true, details: "пачка в день" }, "ru")).toBe("да — пачка в день");
  });

  it("yesno_text: yes without details", () => {
    expect(formatValue(yesnoField, { answer: true, details: "" }, "ru")).toBe("да");
  });

  it("select: translates known value", () => {
    expect(formatValue(selectField, "home", "ru")).toBe("Дома");
    expect(formatValue(selectField, "home", "en")).toBe("Home");
  });

  it("select: unknown value falls back to raw", () => {
    expect(formatValue(selectField, "unknown", "ru")).toBe("unknown");
  });

  it("multiselect: joins translated labels", () => {
    expect(formatValue(multiField, ["health", "weight"], "ru")).toBe("Здоровье, Вес");
  });

  it("multiselect: empty array returns null", () => {
    expect(formatValue(multiField, [], "ru")).toBeNull();
  });
});
