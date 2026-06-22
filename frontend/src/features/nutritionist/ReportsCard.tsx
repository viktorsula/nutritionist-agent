import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { supabase } from "../../lib/supabase";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "../../components/ui/Button";
import { useClientReports, type ReportRow } from "./queries";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function safeFileName(s: string): string {
  return (s || "report").replace(/[^\wа-яё0-9-]+/gi, "_").slice(0, 60);
}

/** Инструмент «Сформировать отчёт» в карточке клиента: генерация агентом по шаблону,
 *  правка нутрициологом, сохранение в client_reports (RLS), выгрузка PDF/TXT. */
export function ReportsCard({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const { appUser } = useAuth();
  const reports = useClientReports(clientId);

  const types = useQuery({
    queryKey: ["report_types"],
    queryFn: () => api.reportTypes(),
  });

  const [reportType, setReportType] = useState("recommendations");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  const typeEntries = Object.entries(types.data ?? { recommendations: "Рекомендации для подопечного" });

  function reset() {
    setCurrentId(null);
    setTitle("");
    setContent("");
    setOk("");
    setError("");
  }

  async function generate() {
    setBusy(true);
    setOk("");
    setError("");
    try {
      const res = await api.generateReport({ client_id: clientId, report_type: reportType });
      setCurrentId(null); // сгенерировано заново — это новый черновик, пока не сохранён
      setTitle(res.title);
      setContent(res.content);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reports.gen_error"));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setOk("");
    setError("");
    try {
      if (currentId) {
        const { error: e } = await supabase
          .from("client_reports")
          .update({ title, content, updated_at: new Date().toISOString() })
          .eq("id", currentId);
        if (e) throw e;
      } else {
        const { data, error: e } = await supabase
          .from("client_reports")
          .insert({
            client_id: clientId,
            report_type: reportType,
            title: title || t("reports.untitled"),
            content,
            created_by: appUser?.user_id ?? null,
          })
          .select("id")
          .single();
        if (e) throw e;
        setCurrentId(data?.id ?? null);
      }
      setOk(t("reports.saved"));
      qc.invalidateQueries({ queryKey: ["client_reports", clientId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reports.save_error"));
    } finally {
      setBusy(false);
    }
  }

  function open(r: ReportRow) {
    setCurrentId(r.id);
    setReportType(r.report_type);
    setTitle(r.title);
    setContent(r.content);
    setOk("");
    setError("");
  }

  function downloadTxt() {
    const blob = new Blob([`${title}\n\n${content}`], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${safeFileName(title)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function downloadPdf() {
    // Печать через браузер (надёжно для кириллицы) → «Сохранить как PDF».
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(
      `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(title)}</title>` +
        `<style>body{font-family:system-ui,Arial,sans-serif;padding:32px;line-height:1.5;}` +
        `h1{font-size:18px;margin:0 0 16px;}div{white-space:pre-wrap;font-size:13px;}</style>` +
        `</head><body><h1>${escapeHtml(title)}</h1><div>${escapeHtml(content)}</div></body></html>`,
    );
    w.document.close();
    w.focus();
    w.print();
  }

  const hasReport = !!(title || content);

  return (
    <div className="space-y-3">
      {/* Выбор типа + генерация */}
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="rounded-md border px-2 py-1 text-sm"
          value={reportType}
          onChange={(e) => setReportType(e.target.value)}
        >
          {typeEntries.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <Button type="button" onClick={generate} disabled={busy}>
          {busy ? t("reports.generating") : t("reports.generate")}
        </Button>
        {hasReport && (
          <button onClick={reset} className="text-xs text-gray-500 hover:text-brand">
            {t("reports.new")}
          </button>
        )}
      </div>

      {/* Редактор отчёта */}
      {hasReport && (
        <div className="space-y-2">
          <input
            className="w-full rounded-md border px-3 py-2 text-sm font-medium"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={t("reports.title_placeholder")}
          />
          <textarea
            className="h-64 w-full resize-y rounded-md border px-3 py-2 text-sm leading-snug"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={t("reports.content_placeholder")}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" onClick={save} disabled={busy}>
              {busy ? t("reports.saving") : t("reports.save")}
            </Button>
            <button
              onClick={downloadPdf}
              className="rounded-md border px-3 py-1 text-xs text-gray-600 hover:bg-brand-light"
            >
              {t("reports.pdf")}
            </button>
            <button
              onClick={downloadTxt}
              className="rounded-md border px-3 py-1 text-xs text-gray-600 hover:bg-brand-light"
            >
              {t("reports.txt")}
            </button>
            {ok && <span className="text-xs text-green-600">{ok}</span>}
            {error && <span className="text-xs text-red-600">{error}</span>}
          </div>
        </div>
      )}

      {!hasReport && error && <div className="text-xs text-red-600">{error}</div>}

      {/* Список сохранённых отчётов */}
      <div className="border-t pt-2">
        <div className="mb-1 text-xs font-medium text-gray-600">{t("reports.saved_list")}</div>
        {(reports.data ?? []).length === 0 ? (
          <div className="text-xs text-gray-400">{t("reports.empty")}</div>
        ) : (
          <ul className="space-y-1 text-xs">
            {(reports.data ?? []).map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => open(r)}
                  className={`flex w-full justify-between gap-2 rounded px-2 py-1 text-left hover:bg-brand-light ${
                    currentId === r.id ? "bg-brand-light" : ""
                  }`}
                >
                  <span className="text-gray-700">{r.title}</span>
                  <span className="shrink-0 text-gray-400">
                    {new Date(r.created_at).toLocaleDateString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
