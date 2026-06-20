import { useQuery } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";

export interface RegistryRow {
  id: string;
  name: string | null;
  client_status: string | null;
  payment_status: string | null;
  access_status: string | null;
  nutritionist_notes: string | null;
  client_profiles: { goals: string | null; weight: number | null; target_weight: number | null } | null;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  due_date: string | null;
  status: string;
  created_by: string;
  created_at: string;
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
          "id,name,client_status,payment_status,access_status,nutritionist_notes,client_profiles(goals,weight,target_weight)",
        )
        .order("name", { ascending: true });
      if (error) throw error;
      return (data ?? []) as unknown as RegistryRow[];
    },
  });
}

/** Задачи клиента (свежие сверху). */
export function useClientTasks(clientId: string) {
  return useQuery({
    queryKey: ["client_tasks", clientId],
    enabled: !!clientId,
    queryFn: async (): Promise<Task[]> => {
      const { data, error } = await supabase
        .from("tasks")
        .select("id,title,description,due_date,status,created_by,created_at")
        .eq("client_id", clientId)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
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
        .limit(15);
      if (error) throw error;
      return data ?? [];
    },
  });
}
