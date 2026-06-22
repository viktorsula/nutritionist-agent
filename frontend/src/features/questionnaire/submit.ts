import { supabase } from "../../lib/supabase";
import { safeStorageName } from "../client/documents";
import { IMPROVE } from "./schema";

export type Answers = Record<string, unknown>;
export type Lang = "ru" | "en";

const STORAGE_BUCKET = "client-documents";

function num(v: unknown): number | null {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function splitList(v: unknown): string[] {
  if (typeof v !== "string" || !v.trim()) return [];
  return v
    .split(/[\n,;]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** yesno_text хранится как {answer: boolean, details: string}. */
function yesnoDetails(v: unknown): string {
  if (v && typeof v === "object" && "details" in v) {
    return String((v as { details?: unknown }).details ?? "");
  }
  return "";
}

function composeGoals(answers: Answers, lang: Lang): string {
  const labels = Object.fromEntries(IMPROVE.map((o) => [o.value, o.label[lang]]));
  const targets = Array.isArray(answers.improve_targets)
    ? (answers.improve_targets as string[]).map((v) => labels[v] ?? v).join(", ")
    : "";
  const text = typeof answers.goal_text === "string" ? answers.goal_text.trim() : "";
  return [targets, text].filter(Boolean).join(" — ");
}

/** Загрузка PDF анализов в Storage + запись в document_metadata (best-effort). */
async function uploadLabFiles(clientId: string, files: File[]): Promise<void> {
  for (const file of files) {
    try {
      const rand = Math.random().toString(36).slice(2, 8);
      const path = `${clientId}/${Date.now()}_${rand}_${safeStorageName(file.name)}`;
      const up = await supabase.storage.from(STORAGE_BUCKET).upload(path, file);
      if (up.error) {
        console.warn("Lab file upload failed (bucket configured?):", up.error.message);
        continue;
      }
      const meta = await supabase.from("document_metadata").insert({
        source: "client_upload",
        client_id: clientId,
        document_type: "client_document",
        file_name: file.name,
        mime_type: file.type || "application/pdf",
        storage_url: path,
        file_size_bytes: file.size,
      });
      if (meta.error) console.warn("document_metadata insert failed:", meta.error.message);
    } catch (e) {
      console.warn("Lab file processing error:", e);
    }
  }
}

/**
 * Сохраняет опросник: client_profiles (полный JSON + ключевые поля),
 * стартовую запись measurements, загружает PDF. Всё под RLS (свой client_id).
 */
export async function submitQuestionnaire(
  clientId: string,
  answers: Answers,
  files: File[],
  lang: Lang = "ru",
): Promise<void> {
  // 1. Профиль клиента (ключевые поля + полный опросник + завершение онбординга)
  const profile = {
    client_id: clientId,
    birth_date: (answers.birth_date as string) || null,
    gender: (answers.gender as string) || null,
    weight: num(answers.weight),
    height: num(answers.height),
    target_weight: num(answers.target_weight),
    activity_level: (answers.sport_level as string) || null,
    allergies: yesnoDetails(answers.allergies)
      ? splitList(yesnoDetails(answers.allergies))
      : [],
    chronic_conditions: splitList(answers.chronic_conditions),
    goals: composeGoals(answers, lang),
    questionnaire_json: answers,
    onboarding_completed_at: new Date().toISOString(),
  };

  const { error: pErr } = await supabase
    .from("client_profiles")
    .upsert(profile, { onConflict: "client_id" });
  if (pErr) throw new Error(pErr.message);

  // 2. Стартовая запись замеров (если есть хоть один показатель)
  const weight = num(answers.weight);
  const neck = num(answers.neck);
  const waist = num(answers.waist);
  const hips = num(answers.hips);
  if (weight !== null || neck !== null || waist !== null || hips !== null) {
    const { error: mErr } = await supabase.from("measurements").insert({
      client_id: clientId,
      measured_at: new Date().toISOString().slice(0, 10),
      weight,
      neck,
      waist,
      hips,
    });
    if (mErr) console.warn("measurements insert failed:", mErr.message);
  }

  // 3. PDF анализов (необязательно, требует настроенного бакета)
  if (files.length > 0) {
    await uploadLabFiles(clientId, files);
  }
}
