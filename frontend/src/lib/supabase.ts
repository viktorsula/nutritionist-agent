import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

if (!url || !anonKey) {
  // Не роняем приложение, но явно сигналим о неполной конфигурации.
  console.warn(
    "VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY не заданы — авторизация не будет работать.",
  );
}

/**
 * Supabase-клиент под anon-ключом. Все запросы к данным идут под JWT пользователя,
 * RLS ограничивает доступ. Сессия сохраняется в localStorage (persistSession).
 */
export const supabase = createClient(url ?? "", anonKey ?? "", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
