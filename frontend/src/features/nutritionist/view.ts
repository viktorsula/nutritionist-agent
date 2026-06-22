/**
 * Директива вида для центральной панели кабинета нутрициолога (Блок 2).
 * Приходит из ответа агента (/nutritionist/query) и переключает центр.
 */
export type CenterView =
  | { type: "client_card"; client_id: string; client_name?: string | null; period_days?: number }
  | { type: "analytics" }
  | { type: "registry" };

/** График, выбранный агентом для панели «Аналитика» (рендерится из реальных данных БД). */
export type AnalysisChart = { kind: "weight" } | { kind: "lab"; indicator: string };

/** Результат аналитики от агента (RAG-конвейер) для панели «Аналитика». */
export interface AgentAnalysis {
  client_id: string | null;
  client_name?: string | null;
  title: string;
  markdown: string;
  charts: AnalysisChart[];
  period_days?: number | null;
}
