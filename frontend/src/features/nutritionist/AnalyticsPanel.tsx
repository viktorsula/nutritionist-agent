import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { supabase } from "../../lib/supabase";
import { daysUntil, SOON_DAYS } from "./expiry";
import { WeightChart, LabChart } from "../client/charts";
import { useMeasurements, useLabResults, useClientProfile } from "../client/queries";
import type { AgentAnalysis } from "./view";

const STATUSES = ["lead", "onboarding", "active", "paused", "completed", "archived"];

interface StatRow {
  client_status: string | null;
  payment_status: string | null;
  paid_until: string | null;
}

/** Агрегаты по всей базе клиентов (под RLS нутрициолог видит всех). */
function useBaseStats() {
  return useQuery({
    queryKey: ["base_stats"],
    queryFn: async (): Promise<StatRow[]> => {
      const { data, error } = await supabase
        .from("clients")
        .select("client_status,payment_status,paid_until");
      if (error) throw error;
      return (data ?? []) as StatRow[];
    },
  });
}

/** Графики анализа агента: рисуются из реальных данных БД по client_id. */
function AnalysisCharts({ analysis }: { analysis: AgentAnalysis }) {
  const { t, i18n } = useTranslation();
  const clientId = analysis.client_id ?? "";
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const measurements = useMeasurements(clientId);
  const labs = useLabResults(clientId);
  const profile = useClientProfile(clientId);

  if (!clientId || analysis.charts.length === 0) return null;
  const tracked = profile.data?.tracked_lab_indicators ?? [];

  return (
    <div className="space-y-4">
      {analysis.charts.map((ch, i) => {
        if (ch.kind === "weight") {
          return (
            <WeightChart
              key={`w${i}`}
              data={measurements.data ?? []}
              target={profile.data?.target_weight}
              emptyText={t("card.no_data")}
            />
          );
        }
        const ind = tracked.find((x) => x.key === ch.indicator);
        const rows = (labs.data ?? []).filter((r) => r.indicator === ch.indicator);
        const unit = ind?.unit ?? rows[0]?.unit ?? null;
        return (
          <LabChart
            key={`l${i}`}
            indicator={ch.indicator}
            label={ind ? (lang === "en" ? ind.label_en : ind.label_ru) : ch.indicator}
            unit={unit}
            refMin={ind?.ref_min ?? null}
            refMax={ind?.ref_max ?? null}
            data={rows}
            emptyText={t("card.no_data")}
          />
        );
      })}
    </div>
  );
}

/** Мини-дашборд аналитики по базе + результат анализа агента (если есть). */
export function AnalyticsPanel({ analysis }: { analysis?: AgentAnalysis | null }) {
  const { t } = useTranslation();
  const stats = useBaseStats();
  const rows = stats.data ?? [];

  const total = rows.length;
  const byStatus = (s: string) => rows.filter((r) => r.client_status === s).length;
  const paidActive = rows.filter((r) => r.payment_status === "active").length;
  const paidInactive = rows.filter((r) => r.payment_status === "inactive").length;
  const expiring = rows.filter((r) => {
    const d = daysUntil(r.paid_until);
    return d !== null && d <= SOON_DAYS;
  }).length;
  const maxStatus = Math.max(1, ...STATUSES.map(byStatus));

  const Stat = ({ label, value, tone }: { label: string; value: number; tone?: string }) => (
    <div className="rounded-md border p-3">
      <div className={`text-2xl font-semibold ${tone ?? "text-gray-800"}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );

  return (
    <div className="max-w-3xl space-y-6">
      {/* Результат анализа агента (RAG-конвейер) */}
      {analysis && (
        <div className="space-y-3 rounded-md border border-brand/30 bg-brand-light/30 p-4">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-brand-dark">{analysis.title}</h3>
            {analysis.client_name && (
              <span className="text-xs text-gray-500">{analysis.client_name}</span>
            )}
          </div>
          <div className="prose prose-sm max-w-none text-sm text-gray-800 [&_h1]:text-base [&_h2]:text-sm [&_h3]:text-sm [&_li]:my-0.5 [&_p]:my-1 [&_ul]:list-disc [&_ul]:pl-5">
            <ReactMarkdown>{analysis.markdown}</ReactMarkdown>
          </div>
          <AnalysisCharts analysis={analysis} />
        </div>
      )}

      {/* Базовый дашборд по всей базе */}
      <div className="space-y-5">
        <h3 className="text-sm font-semibold text-gray-700">{t("analytics.title")}</h3>

        {stats.isLoading ? (
          <div className="text-xs text-gray-400">{t("loading")}</div>
        ) : stats.error ? (
          <div className="text-sm text-red-600">{t("analytics.error")}</div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Stat label={t("analytics.total")} value={total} />
              <Stat label={t("analytics.paid")} value={paidActive} tone="text-green-600" />
              <Stat label={t("analytics.unpaid")} value={paidInactive} tone="text-red-600" />
              <Stat label={t("analytics.expiring")} value={expiring} tone="text-amber-600" />
            </div>

            <div>
              <div className="mb-2 text-xs font-medium text-gray-600">{t("analytics.funnel")}</div>
              <div className="space-y-1">
                {STATUSES.map((s) => {
                  const n = byStatus(s);
                  return (
                    <div key={s} className="flex items-center gap-2 text-xs">
                      <span className="w-24 shrink-0 text-gray-500">
                        {t(`registry.status_value.${s}`, { defaultValue: s })}
                      </span>
                      <div className="h-4 flex-1 rounded bg-gray-100">
                        <div
                          className="h-4 rounded bg-brand"
                          style={{ width: `${(n / maxStatus) * 100}%` }}
                        />
                      </div>
                      <span className="w-6 shrink-0 text-right text-gray-700">{n}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
