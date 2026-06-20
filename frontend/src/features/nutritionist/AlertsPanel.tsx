import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";

type Severity = "critical" | "high" | "medium";
const SEVERITIES: Severity[] = ["critical", "high", "medium"];

interface AlertRow {
  id: string;
  event_type: string;
  severity: Severity;
  event_date: string;
  payload_json: Record<string, unknown> | null;
  clients: { name: string | null } | null;
}

const WINDOWS: { key: string; hours: number }[] = [
  { key: "24h", hours: 24 },
  { key: "7d", hours: 24 * 7 },
  { key: "30d", hours: 24 * 30 },
];

const sinceIso = (hours: number) => new Date(Date.now() - hours * 3_600_000).toISOString();

const SEVERITY_STYLE: Record<Severity, string> = {
  critical: "border-l-red-600 bg-red-50",
  high: "border-l-orange-500 bg-orange-50",
  medium: "border-l-amber-400 bg-amber-50",
};

function useAlerts(hours: number, severity: Severity | "all") {
  return useQuery({
    queryKey: ["alerts", hours, severity],
    queryFn: async (): Promise<AlertRow[]> => {
      let q = supabase
        .from("client_events")
        .select("id,event_type,severity,event_date,payload_json,clients!inner(name)")
        .gte("event_date", sinceIso(hours))
        .order("event_date", { ascending: false })
        .limit(200);
      q = severity === "all" ? q.in("severity", SEVERITIES) : q.eq("severity", severity);
      const { data, error } = await q;
      if (error) throw error;
      return (data ?? []) as unknown as AlertRow[];
    },
  });
}

/** Панель алертов нутрициолога: события клиентов с severity (из client_events). */
export function AlertsPanel() {
  const { t } = useTranslation();
  const [winHours, setWinHours] = useState(24 * 7);
  const [severity, setSeverity] = useState<Severity | "all">("all");
  const alerts = useAlerts(winHours, severity);

  function typeLabel(eventType: string): string {
    const key = `alerts.type.${eventType}`;
    const tr = t(key);
    return tr === key ? eventType : tr;
  }

  function message(a: AlertRow): string {
    const p = a.payload_json ?? {};
    if (a.event_type === "bad_wellbeing")
      return (p.reason as string) || (p.answer as string) || "";
    if (a.event_type === "weight_increase") return (p.message as string) || "";
    if (a.event_type === "calories_logged") {
      const arr = (p.alerts as Array<{ message?: string }> | undefined) ?? [];
      return arr.map((x) => x.message).filter(Boolean).join("; ");
    }
    return (p.message as string) || "";
  }

  const rows = alerts.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.key}
              onClick={() => setWinHours(w.hours)}
              className={`rounded-md px-3 py-1 text-xs ${
                winHours === w.hours ? "bg-brand text-white" : "bg-gray-100 text-gray-600"
              }`}
            >
              {t(`alerts.window.${w.key}`)}
            </button>
          ))}
        </div>
        <select
          className="rounded-md border px-2 py-1 text-sm"
          value={severity}
          onChange={(e) => setSeverity(e.target.value as Severity | "all")}
        >
          <option value="all">{t("alerts.sev.all")}</option>
          <option value="critical">{t("alerts.sev.critical")}</option>
          <option value="high">{t("alerts.sev.high")}</option>
          <option value="medium">{t("alerts.sev.medium")}</option>
        </select>
        <button
          onClick={() => alerts.refetch()}
          className="rounded-md bg-gray-100 px-3 py-1 text-xs text-gray-600 hover:bg-brand-light"
        >
          {t("alerts.refresh")}
        </button>
        <span className="text-xs text-gray-400">{t("alerts.count", { n: rows.length })}</span>
      </div>

      {alerts.isLoading ? (
        <div className="text-xs text-gray-400">{t("loading")}</div>
      ) : alerts.error ? (
        <div className="text-sm text-red-600">{t("alerts.error")}</div>
      ) : rows.length === 0 ? (
        <div className="py-8 text-center text-xs text-gray-400">{t("alerts.empty")}</div>
      ) : (
        <ul className="space-y-2">
          {rows.map((a) => (
            <li
              key={a.id}
              className={`rounded-md border border-l-4 p-3 ${SEVERITY_STYLE[a.severity]}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-gray-800">
                  {a.clients?.name || "—"}
                </span>
                <span className="text-[11px] uppercase text-gray-500">
                  {t(`alerts.sev.${a.severity}`)}
                </span>
              </div>
              <div className="text-xs text-gray-600">
                {typeLabel(a.event_type)}
                {message(a) ? ` — ${message(a)}` : ""}
              </div>
              <div className="mt-0.5 text-[11px] text-gray-400">
                {new Date(a.event_date).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
