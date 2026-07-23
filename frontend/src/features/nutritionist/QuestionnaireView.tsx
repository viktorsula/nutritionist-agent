import { useTranslation } from "react-i18next";
import { QUESTIONNAIRE, type Field } from "../questionnaire/schema";

type Lang = "ru" | "en";
type Answers = Record<string, unknown>;

export function formatValue(field: Field, value: unknown, lang: Lang): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (field.type === "file") return null; // файлы — в блоке документов клиента, не здесь

  if (field.type === "yesno_text") {
    if (typeof value !== "object" || value === null) return null;
    const v = value as { answer?: boolean; details?: string };
    if (!v.answer) return lang === "ru" ? "нет" : "no";
    const yes = lang === "ru" ? "да" : "yes";
    return v.details ? `${yes} — ${v.details}` : yes;
  }

  if (field.type === "multiselect" && Array.isArray(value)) {
    const labels = Object.fromEntries((field.options ?? []).map((o) => [o.value, o.label[lang]]));
    const text = value.map((v) => labels[String(v)] ?? String(v)).join(", ");
    return text || null;
  }

  if (field.type === "select" && field.options) {
    const opt = field.options.find((o) => o.value === value);
    return opt ? opt.label[lang] : String(value);
  }

  const unit = field.unit ? ` ${field.unit}` : "";
  return `${String(value)}${unit}`;
}

/** Read-only просмотр заполненной анкеты онбординга, по тем же 6 шагам, что у клиента. */
export function QuestionnaireView({ answers }: { answers: Answers | null | undefined }) {
  const { t, i18n } = useTranslation();
  const lang: Lang = i18n.resolvedLanguage === "en" ? "en" : "ru";

  const steps = QUESTIONNAIRE.map((step) => ({
    step,
    rows: step.fields
      .map((field) => ({ field, value: formatValue(field, answers?.[field.id], lang) }))
      .filter((r): r is { field: Field; value: string } => r.value !== null),
  })).filter((s) => s.rows.length > 0);

  if (steps.length === 0) {
    return <div className="text-xs text-gray-400">{t("questionnaire_view.empty")}</div>;
  }

  return (
    <div className="space-y-3">
      {steps.map(({ step, rows }) => (
        <div key={step.id}>
          <div className="mb-1 text-xs font-semibold text-gray-600">{step.title[lang]}</div>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
            {rows.map(({ field, value }) => (
              <div key={field.id} className="flex gap-1">
                <dt className="shrink-0 text-gray-500">{field.label[lang]}:</dt>
                <dd className="text-gray-800">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
