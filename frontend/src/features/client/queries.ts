import { useQuery } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { api } from "../../lib/api";

/** Показатель анализов, выбранный нутрициологом для графика динамики клиента. */
export interface TrackedIndicator {
  key: string; // совпадает с lab_results.indicator
  label_ru: string;
  label_en: string;
  unit: string | null;
  ref_min: number | null;
  ref_max: number | null;
  order?: number;
}

export interface ClientProfile {
  goals: string | null;
  weight: number | null;
  height: number | null;
  target_weight: number | null;
  birth_date: string | null;
  gender: string | null;
  allergies: string[] | null;
  intolerances: string[] | null;
  chronic_conditions: string[] | null;
  restrictions: string[] | null;
  activity_level: string | null;
  tracked_lab_indicators: TrackedIndicator[] | null;
  questionnaire_json: Record<string, unknown> | null;
}

export interface WellnessPlan {
  sleep_target: string | null;
  activity_target: string | null;
  recovery: string | null;
  stress_management: string | null;
  notes: string | null;
}

export interface NutritionPlan {
  title: string | null;
  plan_json: Record<string, unknown> | null;
  supplements_json: Record<string, unknown> | null;
  effective_from: string | null;
}

export interface Measurement {
  measured_at: string;
  weight: number | null;
  neck: number | null;
  waist: number | null;
  hips: number | null;
}

export interface LabResult {
  measured_at: string;
  indicator: string;
  value: number | null;
  unit: string | null;
}

export interface ClientEvent {
  event_date: string;
  event_type: string;
  payload_json: Record<string, unknown> | null;
}

export function useClientProfile(clientId: string) {
  return useQuery({
    queryKey: ["client_profile", clientId],
    queryFn: async (): Promise<ClientProfile | null> => {
      const { data, error } = await supabase
        .from("client_profiles")
        .select(
          "goals,weight,height,target_weight,birth_date,gender,allergies,intolerances,chronic_conditions,restrictions,activity_level,tracked_lab_indicators,questionnaire_json",
        )
        .eq("client_id", clientId)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useWellnessPlan(clientId: string) {
  return useQuery({
    queryKey: ["wellness_plan", clientId],
    queryFn: async (): Promise<WellnessPlan | null> => {
      const { data, error } = await supabase
        .from("wellness_plans")
        .select("sleep_target,activity_target,recovery,stress_management,notes")
        .eq("client_id", clientId)
        .order("created_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useActivePlan(clientId: string) {
  return useQuery({
    queryKey: ["active_plan", clientId],
    queryFn: async (): Promise<NutritionPlan | null> => {
      const { data, error } = await supabase
        .from("nutrition_plans")
        .select("title,plan_json,supplements_json,effective_from")
        .eq("client_id", clientId)
        .eq("is_active", true)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });
}

export function useMeasurements(clientId: string) {
  return useQuery({
    queryKey: ["measurements", clientId],
    queryFn: async (): Promise<Measurement[]> => {
      const { data, error } = await supabase
        .from("measurements")
        .select("measured_at,weight,neck,waist,hips")
        .eq("client_id", clientId)
        .order("measured_at", { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
  });
}

export function useLabResults(clientId: string) {
  return useQuery({
    queryKey: ["lab_results", clientId],
    queryFn: async (): Promise<LabResult[]> => {
      const { data, error } = await supabase
        .from("lab_results")
        .select("measured_at,indicator,value,unit")
        .eq("client_id", clientId)
        .order("measured_at", { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
  });
}

export function useCalorieEvents(clientId: string) {
  return useQuery({
    queryKey: ["calorie_events", clientId],
    queryFn: async (): Promise<ClientEvent[]> => {
      const { data, error } = await supabase
        .from("client_events")
        .select("event_date,event_type,payload_json")
        .eq("client_id", clientId)
        .eq("event_type", "calories_logged")
        .order("event_date", { ascending: false })
        .limit(30);
      if (error) throw error;
      return data ?? [];
    },
  });
}

/**
 * Суточные тоталы питания (ккал/Б/Ж/У/сахар/вода) + нормы — с бэкенда (общая агрегация
 * для кабинета клиента и нутрициолога). Клиент: свои данные по токену; нутрициолог: любого.
 */
export function useNutritionDaily(clientId: string, days = 14) {
  return useQuery({
    queryKey: ["nutrition_daily", clientId, days],
    queryFn: () => api.nutritionDaily(clientId, days),
    enabled: !!clientId,
  });
}
