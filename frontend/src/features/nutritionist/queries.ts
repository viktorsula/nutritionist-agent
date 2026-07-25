import { useQuery } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { api, type Reminder, type ControlledMetric } from "../../lib/api";

export interface RegistryRow {
  id: string;
  name: string | null;
  client_status: string | null;
  payment_status: string | null;
  access_status: string | null;
  paid_until: string | null;
  nutritionist_notes: string | null;
  telegram_id?: number | null;
  client_profiles: { goals: string | null; weight: number | null; target_weight: number | null } | null;
}


export interface EventRow {
  event_type: string;
  severity: string | null;
  event_date: string;
  payload_json: Record<string, unknown> | null;
}

/** Список клиентов для реестра (под RLS нутрициолог видит всех). */
export function useClientsList() {
  return useQuery({
    queryKey: ["registry_clients"],
    queryFn: async (): Promise<RegistryRow[]> => {
      const { data, error } = await supabase
        .from("clients")
        .select(
          "id,name,client_status,payment_status,access_status,paid_until,nutritionist_notes,client_profiles(goals,weight,target_weight)",
        )
        .order("name", { ascending: true });
      if (error) throw error;
      return (data ?? []) as unknown as RegistryRow[];
    },
  });
}

export interface ReportRow {
  id: string;
  report_type: string;
  title: string;
  content: string;
  status: string;
  created_at: string;
  updated_at: string;
}

/** Сохранённые отчёты клиента (свежие сверху). */
export function useClientReports(clientId: string) {
  return useQuery({
    queryKey: ["client_reports", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<ReportRow[]> => {
      const { data, error } = await supabase
        .from("client_reports")
        .select("id,report_type,title,content,status,created_at,updated_at")
        .eq("client_id", clientId)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });
}

/** Одна строка реестра по client_id (для карточки, открытой из чата). */
export function useClientRow(clientId: string) {
  return useQuery({
    queryKey: ["client_row", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<RegistryRow | null> => {
      const { data, error } = await supabase
        .from("clients")
        .select(
          "id,name,client_status,payment_status,access_status,paid_until,nutritionist_notes,telegram_id,client_profiles(goals,weight,target_weight)",
        )
        .eq("id", clientId)
        .maybeSingle();
      if (error) throw error;
      return (data as unknown as RegistryRow) ?? null;
    },
  });
}

/** Напоминания клиента (через бэкенд — таблица под RLS недоступна фронту напрямую). */
export function useClientReminders(clientId: string) {
  return useQuery({
    queryKey: ["client_reminders", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<Reminder[]> => (await api.listReminders(clientId)).reminders,
  });
}

/** Каталог контролируемых показателей клиента (через бэкенд). */
export function useControlledMetrics(clientId: string) {
  return useQuery({
    queryKey: ["controlled_metrics", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<ControlledMetric[]> =>
      (await api.listControlledMetrics(clientId)).metrics,
  });
}

export interface WellnessRow {
  id: string;
  sleep_target: string | null;
  activity_target: string | null;
  recovery: string | null;
  stress_management: string | null;
  notes: string | null;
}

/** Последний ЗОЖ-план клиента (с id — для редактирования). */
export function useWellnessRow(clientId: string) {
  return useQuery({
    queryKey: ["wellness_row", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<WellnessRow | null> => {
      const { data, error } = await supabase
        .from("wellness_plans")
        .select("id,sleep_target,activity_target,recovery,stress_management,notes")
        .eq("client_id", clientId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export interface PlanRow {
  id: string;
  version: number;
  title: string;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  plan_json: {
    description?: string | null;
    target_calories?: number | null;
    restrictions?: string[] | null;
  } | null;
  supplements_json: { items?: string[] } | null;
}

/** История планов питания клиента (все версии, свежие сверху). */
export function useClientPlans(clientId: string) {
  return useQuery({
    queryKey: ["client_plans", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<PlanRow[]> => {
      const { data, error } = await supabase
        .from("nutrition_plans")
        .select("id,version,title,effective_from,effective_to,is_active,plan_json,supplements_json")
        .eq("client_id", clientId)
        .order("version", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });
}

export interface QuestionnaireHistoryRow {
  id: string;
  questionnaire_json: Record<string, unknown>;
  submitted_at: string;
}

/** История версий анкеты клиента (миграция 017) — свежие сверху. */
export function useQuestionnaireHistory(clientId: string) {
  return useQuery({
    queryKey: ["questionnaire_history", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<QuestionnaireHistoryRow[]> => {
      const { data, error } = await supabase
        .from("client_questionnaire_history")
        .select("id,questionnaire_json,submitted_at")
        .eq("client_id", clientId)
        .order("submitted_at", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });
}

/** Открытые находки проактивного аудита клиента (NEW-1) — через бэкенд (RLS: только нутрициолог). */
export function useAuditFindings(clientId: string) {
  return useQuery({
    queryKey: ["audit_findings", clientId],
    enabled: !!clientId,
    queryFn: () => api.listAuditFindings(clientId).then((r) => r.findings),
  });
}

/** Недавние события клиента (журнал + алерты). */
export function useClientEventsRecent(clientId: string) {
  return useQuery({
    queryKey: ["client_events_recent", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<EventRow[]> => {
      const { data, error } = await supabase
        .from("client_events")
        .select("event_type,severity,event_date,payload_json")
        .eq("client_id", clientId)
        .order("event_date", { ascending: false })
        .limit(50);
      if (error) throw error;
      return data ?? [];
    },
  });
}
