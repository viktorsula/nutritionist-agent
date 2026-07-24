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

/** Запись реестра промптов (см. бэкенд prompts/registry.py). */
export interface PromptMeta {
  key: string;
  label_ru: string;
  label_en: string;
  section: "communication" | "system";
  llm: string;
  source: "db" | "file";
  editable: boolean;
}

export interface KnowledgeDoc {
  id: string;
  title: string | null;
  file_name: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  created_at: string;
}

export interface NutritionDay {
  date: string;
  kcal: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  sugar_g: number;
  water_ml: number;
}

export interface NutritionDaily {
  client_id: string;
  days: number;
  series: NutritionDay[];
  targets: { kcal?: number; water_ml?: number };
}

export interface Reminder {
  id: string;
  client_id: string;
  title: string;
  remind_at: string; // 'HH:MM:SS'
  recurrence: "once" | "daily" | "weekly";
  weekday: number | null; // 0=Пн … 6=Вс
  remind_date: string | null;
  requires_response: boolean;
  expected_response: string | null; // ключ показателя | 'text' | null
  response_deadline?: string | null; // 'HH:MM' дедлайн отчёта (еда: 12/17/22)
  followup_after_hours?: number | null;
  max_followups?: number | null;
  active: boolean;
}

export interface ReminderInput {
  title: string;
  remind_at: string; // 'HH:MM'
  recurrence: "once" | "daily" | "weekly";
  weekday?: number | null;
  remind_date?: string | null;
  requires_response?: boolean;
  expected_response?: string | null;
  response_deadline?: string | null; // 'HH:MM' дедлайн отчёта (еда: 12/17/22)
  followup_after_hours?: number | null;
  max_followups?: number | null;
}

/** Текст согласия на обработку данных (LEGAL-1, миграция 018) — гранулярные пункты. */
export interface ConsentText {
  version: string;
  ru: { health_data: string; telegram_channel: string };
  en: { health_data: string; telegram_channel: string };
}

/** Контролируемый показатель клиента (каталог). */
export interface ControlledMetric {
  key: string;
  label_ru: string;
  label_en?: string;
  unit: string;
  category?: "physical" | "sleep" | "custom";
}

export const api = {
  /** Текущий пользователь (роль, client_id, статусы) — авторитетно из БД. */
  me: () => request<AppUser>("/me"),

  /** Напоминания клиента (для редактора нутрициолога). */
  listReminders: (clientId: string) =>
    request<{ reminders: Reminder[] }>(`/clients/${encodeURIComponent(clientId)}/reminders`),

  /** Создать напоминание клиенту (с аудитом). */
  createReminder: (clientId: string, body: ReminderInput) =>
    request<{ reminder: Reminder }>(`/clients/${encodeURIComponent(clientId)}/reminders`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Обновить напоминание (partial). */
  updateReminder: (clientId: string, reminderId: string, body: Partial<ReminderInput> & { active?: boolean }) =>
    request<{ reminder: Reminder }>(
      `/clients/${encodeURIComponent(clientId)}/reminders/${encodeURIComponent(reminderId)}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),

  /** Удалить напоминание. */
  deleteReminder: (clientId: string, reminderId: string) =>
    request<{ ok: boolean }>(
      `/clients/${encodeURIComponent(clientId)}/reminders/${encodeURIComponent(reminderId)}`,
      { method: "DELETE" },
    ),

  /** Каталог контролируемых показателей клиента. */
  listControlledMetrics: (clientId: string) =>
    request<{ metrics: ControlledMetric[] }>(
      `/clients/${encodeURIComponent(clientId)}/controlled-metrics`,
    ),

  /** Перезаписать каталог контролируемых показателей клиента. */
  setControlledMetrics: (clientId: string, metrics: ControlledMetric[]) =>
    request<{ metrics: ControlledMetric[] }>(
      `/clients/${encodeURIComponent(clientId)}/controlled-metrics`,
      { method: "PUT", body: JSON.stringify({ metrics }) },
    ),

  /**
   * Суточные тоталы питания (ккал/Б/Ж/У/сахар/вода) + нормы из плана.
   * Клиент: client_id из токена (аргумент игнорируется сервером). Нутрициолог: обязателен.
   */
  nutritionDaily: (clientId?: string, days = 14) =>
    request<NutritionDaily>(
      `/nutrition/daily?days=${days}` +
        (clientId ? `&client_id=${encodeURIComponent(clientId)}` : ""),
    ),

  /** Сообщение клиента агенту. */
  chat: (message: string, messageType = "text") =>
    request<Record<string, unknown>>("/chat", {
      method: "POST",
      body: JSON.stringify({ message, message_type: messageType }),
    }),

  /**
   * Пересобрать саммари анкеты + уведомить нутрициолога (миграция 017). Вызывается после
   * отправки анкеты (первичной/повторной) — client_id из токена.
   */
  questionnaireSummary: () =>
    request<{ summary: string | null }>("/questionnaire-summary", { method: "POST" }),

  /** Текущий текст согласия на обработку данных (LEGAL-1, миграция 018). */
  consentText: () => request<ConsentText>("/consent-text"),

  /** Зафиксировать согласие клиента (LEGAL-1/LEGAL-5) — оба пункта обязательны. */
  acceptConsent: (payload: {
    health_data: boolean;
    telegram_channel: boolean;
  }) =>
    request<{ ok: boolean }>("/consent", {
      method: "POST",
      body: JSON.stringify(payload),
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
    phone?: string | null;
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

  /** Провайдеры LLM: какие доступны (ключ задан) из всех известных. */
  llmProviders: () =>
    request<{ available: string[]; all: string[] }>("/nutritionist/llm/providers"),

  /** Живой список моделей провайдера (ListModels, кэш на бэке). */
  llmModels: (provider: string) =>
    request<{ provider: string; models: string[] }>(
      `/nutritionist/llm/models?provider=${encodeURIComponent(provider)}`,
    ),

  /** Мини-пинг модели перед сохранением. */
  llmTest: (provider: string, model: string) =>
    request<{ ok: boolean; latency_ms: number; model: string; error: string | null }>(
      "/nutritionist/llm/test",
      { method: "POST", body: JSON.stringify({ provider, model }) },
    ),

  /** Код-дефолты llm_config (для «Сбросить на дефолт»). */
  llmDefaults: () => request<Record<string, unknown>>("/nutritionist/llm/defaults"),

  /** Реестр промптов с понятными названиями, разделом и источником значения. */
  promptsList: () => request<PromptMeta[]>("/nutritionist/prompts"),

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

  /** Создать одноразовую ссылку привязки Telegram для клиента (nutritionist). */
  telegramLink: (clientId: string) =>
    request<{ token: string; deep_link: string; expires_at: string; configured: boolean }>(
      `/clients/${encodeURIComponent(clientId)}/telegram-link`,
      { method: "POST" },
    ),

  /** Отвязать Telegram от клиента (обнуляет telegram_id и активный токен). */
  telegramUnlink: (clientId: string) =>
    request<{ ok: boolean }>(`/clients/${encodeURIComponent(clientId)}/telegram-link`, {
      method: "DELETE",
    }),

  /** Сбросить пароль клиента (nutritionist): задаёт временный пароль, возвращает его для показа. */
  resetClientPassword: (clientId: string) =>
    request<{
      password: string;
      client_email: string | null;
      email_sent: boolean;
      email_reason: string;
      sent_to: string;
    }>(`/clients/${encodeURIComponent(clientId)}/reset-password`, { method: "POST" }),

  /** Обновление статусов клиента (жизненный цикл + оплата + срок) с аудитом на бэкенде. */
  updateClientStatus: (
    clientId: string,
    body: { client_status?: string; payment_status?: string; paid_until?: string },
  ) =>
    request<{ ok: boolean }>(`/clients/${encodeURIComponent(clientId)}/status`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
