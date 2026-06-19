import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/Header";
import { QUESTIONNAIRE, type Field } from "./schema";
import { submitQuestionnaire, type Answers } from "./submit";

type Lang = "ru" | "en";

interface Props {
  clientId: string;
  onDone: () => void;
}

export function Questionnaire({ clientId, onDone }: Props) {
  const { t, i18n } = useTranslation();
  const lang: Lang = i18n.resolvedLanguage === "en" ? "en" : "ru";

  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const step = QUESTIONNAIRE[stepIndex];
  const isLast = stepIndex === QUESTIONNAIRE.length - 1;

  const setVal = (id: string, value: unknown) =>
    setAnswers((prev) => ({ ...prev, [id]: value }));

  function isFilled(field: Field): boolean {
    const v = answers[field.id];
    if (field.type === "multiselect") return Array.isArray(v) && v.length > 0;
    if (field.type === "file") return files.length > 0;
    return v !== undefined && v !== null && String(v).trim() !== "";
  }

  function validateStep(): boolean {
    const missing = step.fields.filter((f) => f.required && !isFilled(f));
    if (missing.length > 0) {
      setError(t("questionnaire.required_error"));
      return false;
    }
    setError("");
    return true;
  }

  async function next() {
    if (!validateStep()) return;
    if (!isLast) {
      setStepIndex((i) => i + 1);
      return;
    }
    setBusy(true);
    try {
      await submitQuestionnaire(clientId, answers, files, lang);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("questionnaire.submit_error"));
    } finally {
      setBusy(false);
    }
  }

  function back() {
    setError("");
    setStepIndex((i) => Math.max(0, i - 1));
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="mx-auto max-w-2xl p-4">
        <div className="rounded-xl bg-white p-6 shadow-sm">
          <div className="mb-1 text-xs text-gray-400">
            {t("questionnaire.step", {
              current: stepIndex + 1,
              total: QUESTIONNAIRE.length,
            })}
          </div>
          <h1 className="mb-4 text-lg font-semibold text-brand-dark">
            {step.title[lang]}
          </h1>

          <div className="space-y-4">
            {step.fields.map((field) => (
              <FieldInput
                key={field.id}
                field={field}
                lang={lang}
                value={answers[field.id]}
                onChange={(v) => setVal(field.id, v)}
                onFiles={setFiles}
                files={files}
              />
            ))}
          </div>

          {error && <div className="mt-4 text-sm text-red-600">{error}</div>}

          <div className="mt-6 flex justify-between">
            <Button variant="outline" onClick={back} disabled={stepIndex === 0 || busy}>
              {t("questionnaire.back")}
            </Button>
            <Button onClick={next} disabled={busy}>
              {busy
                ? t("questionnaire.submitting")
                : isLast
                ? t("questionnaire.submit")
                : t("questionnaire.next")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ========================================
// Рендер одного поля по типу
// ========================================

interface FieldProps {
  field: Field;
  lang: Lang;
  value: unknown;
  onChange: (v: unknown) => void;
  files: File[];
  onFiles: (f: File[]) => void;
}

function FieldInput({ field, lang, value, onChange, files, onFiles }: FieldProps) {
  const { t } = useTranslation();
  const label = field.label[lang] + (field.unit ? ` (${field.unit})` : "");
  const base = "w-full rounded-md border px-3 py-2 text-sm";

  const labelEl = (
    <label className="mb-1 block text-sm text-gray-700">
      {label}
      {field.required && <span className="text-red-500"> *</span>}
    </label>
  );

  switch (field.type) {
    case "textarea":
      return (
        <div>
          {labelEl}
          <textarea
            rows={3}
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );

    case "number":
      return (
        <div>
          {labelEl}
          <input
            type="number"
            step="any"
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );

    case "date":
      return (
        <div>
          {labelEl}
          <input
            type="date"
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );

    case "time":
      return (
        <div>
          {labelEl}
          <input
            type="time"
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );

    case "select":
      return (
        <div>
          {labelEl}
          <select
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          >
            <option value="">—</option>
            {field.options?.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label[lang]}
              </option>
            ))}
          </select>
        </div>
      );

    case "multiselect": {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      const toggle = (v: string) =>
        onChange(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
      return (
        <div>
          {labelEl}
          <div className="flex flex-wrap gap-3">
            {field.options?.map((o) => (
              <label key={o.value} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={arr.includes(o.value)}
                  onChange={() => toggle(o.value)}
                />
                {o.label[lang]}
              </label>
            ))}
          </div>
        </div>
      );
    }

    case "yesno_text": {
      const obj = (value as { answer?: boolean; details?: string }) ?? {};
      return (
        <div>
          {labelEl}
          <div className="mb-2 flex gap-4 text-sm">
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={obj.answer === true}
                onChange={() => onChange({ ...obj, answer: true })}
              />
              {t("questionnaire.yes")}
            </label>
            <label className="flex items-center gap-1">
              <input
                type="radio"
                checked={obj.answer === false}
                onChange={() => onChange({ ...obj, answer: false })}
              />
              {t("questionnaire.no")}
            </label>
          </div>
          {obj.answer === true && (
            <textarea
              rows={2}
              className={base}
              value={obj.details ?? ""}
              onChange={(e) => onChange({ ...obj, details: e.target.value })}
            />
          )}
        </div>
      );
    }

    case "file":
      return (
        <div>
          {labelEl}
          <input
            type="file"
            accept="application/pdf"
            multiple={field.multiple}
            className="text-sm"
            onChange={(e) => onFiles(Array.from(e.target.files ?? []))}
          />
          {files.length > 0 && (
            <div className="mt-1 text-xs text-gray-500">
              {files.map((f) => f.name).join(", ")}
            </div>
          )}
          <div className="mt-1 text-xs text-gray-400">{t("questionnaire.upload_hint")}</div>
        </div>
      );

    case "text":
    default:
      return (
        <div>
          {labelEl}
          <input
            type="text"
            className={base}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
          />
        </div>
      );
  }
}
