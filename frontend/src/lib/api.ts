import { supabase } from "./supabase";
import type { AppUser } from "../types";

const API_URL = import.meta.env.VITE_API_URL ?? "";

/** Текущий access token из сессии Supabase. */
async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(init.headers ?? {}),
  };
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  /** Текущий пользователь (роль, client_id, статусы) — авторитетно из БД. */
  me: () => request<AppUser>("/me"),

  /** Сообщение клиента агенту. */
  chat: (message: string, messageType = "text") =>
    request<Record<string, unknown>>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, message_type: messageType }),
    }),

  /** Запрос нутрициолога к агенту. */
  nutritionistQuery: (message: string) =>
    request<Record<string, unknown>>("/nutritionist/query", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  /** Создать аккаунт клиента (приглашение по email) — для нутрициолога. */
  createClient: (payload: {
    email: string;
    name: string;
    timezone?: string;
    language?: string;
  }) =>
    request<{ client_id: string; user_id: string; email: string }>("/clients", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
