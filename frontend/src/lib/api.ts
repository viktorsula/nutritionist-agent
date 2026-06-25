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

/** Multipart-загрузка файла (Content-Type ставит браузер с boundary — не задаём). */
async function upload<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...(await authHeader()) },
    body: form,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export interface KnowledgeDoc {
  id: string;
  title: string | null;
  file_name: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  created_at: string;
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
    paid: boolean;
    mode: "basic" | "full";
    paid_until?: string | null;
  }) =>
    request<{ client_id: string; user_id: string; email: string }>("/clients", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Сохранить настройку system_settings (через бэкенд: upsert + audit_log). */
  saveSetting: (key: string, value: unknown) =>
    request<{ ok: boolean }>("/nutritionist/setting", {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),

  /** Список промптов {name: {source, ...}}. */
  promptsList: () => request<Record<string, { source: string }>>("/nutritionist/prompts"),

  /** Текущий текст промпта. */
  promptLoad: (name: string) =>
    request<{ name: string; text: string }>(`/nutritionist/prompt?name=${encodeURIComponent(name)}`),

  /** Сохранить промпт в БД. */
  promptSave: (payload: { name: string; text: string; description?: string }) =>
    request<{ ok: boolean }>("/nutritionist/prompt", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Векторизовать загруженный документ клиента (chunks → pgvector). */
  ingestDocument: (documentId: string) =>
    request<{ document_id: string; chunks: number; note?: string }>(
      `/documents/${encodeURIComponent(documentId)}/ingest`,
      { method: "POST" },
    ),

  /** Список документов базы знаний нутрициолога. */
  knowledgeList: () =>
    request<{ documents: KnowledgeDoc[] }>("/nutritionist/knowledge"),

  /** Загрузить документ в базу знаний (PDF/текст). */
  knowledgeUpload: (file: File, title?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (title?.trim()) form.append("title", title.trim());
    return upload<{ document_id: string; title: string; chunks: number }>(
      "/nutritionist/knowledge",
      form,
    );
  },

  /** Удалить документ базы знаний и его чанки. */
  knowledgeDelete: (documentId: string) =>
    request<{ ok: boolean }>(`/nutritionist/knowledge/${encodeURIComponent(documentId)}`, {
      method: "DELETE",
    }),

  /** Доступные типы отчётов {report_type: title}. */
  reportTypes: () => request<Record<string, string>>("/nutritionist/report-types"),

  /** Сформировать отчёт по клиенту (агент по шаблону). */
  generateReport: (payload: { client_id: string; report_type: string }) =>
    request<{ report_type: string; title: string; content: string }>("/nutritionist/report", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
