export type Role = "client" | "nutritionist" | "observer";

/** Прикладной пользователь — отдаётся API GET /me (резолв из БД по JWT). */
export interface AppUser {
  auth_id: string;
  user_id: string;
  role: Role;
  email: string | null;
  client_id: string | null;
  name?: string | null;
  client_status?: string | null;
  payment_status?: string | null;
  access_status?: string | null;
  language?: string | null;
  timezone?: string | null;
  /** Допуск в веб-кабинет (бизнес-правило: оплата/заморозка/архив). */
  web_allowed?: boolean;
  web_message?: string;
  /** Тариф для отображения: 'full' (Активный) | 'basic' (Базовый). */
  tier?: "full" | "basic" | null;
}
