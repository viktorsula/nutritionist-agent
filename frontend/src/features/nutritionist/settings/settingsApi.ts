import { supabase } from "../../../lib/supabase";

/** Чтение значения настройки system_settings по ключу (null — не задано). */
export async function readSetting(key: string): Promise<unknown> {
  const { data, error } = await supabase
    .from("system_settings")
    .select("value")
    .eq("key", key)
    .maybeSingle();
  if (error) throw error;
  return data?.value ?? null;
}

/** Запись значения настройки (upsert по key, под RLS нутрициолога). */
export async function saveSetting(key: string, value: unknown, userId?: string | null): Promise<void> {
  const { error } = await supabase.from("system_settings").upsert(
    { key, value, updated_by: userId ?? null, updated_at: new Date().toISOString() },
    { onConflict: "key" },
  );
  if (error) throw error;
}
