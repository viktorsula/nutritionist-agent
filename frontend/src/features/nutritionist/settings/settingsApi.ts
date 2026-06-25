import { supabase } from "../../../lib/supabase";
import { api } from "../../../lib/api";

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

/**
 * Запись настройки — через бэкенд (upsert + audit_log).
 * Раньше писали напрямую в Supabase (мимо аудита, №6). updated_by берётся из токена
 * на бэкенде, поэтому userId-аргумент больше не используется (оставлен для совместимости).
 */
export async function saveSetting(key: string, value: unknown, _userId?: string | null): Promise<void> {
  await api.saveSetting(key, value);
}
