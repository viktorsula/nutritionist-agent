import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api, type AuditLogEntry } from "../../lib/api";
import { Button } from "../../components/ui/Button";

const ENTITY_TYPES = [
  "client", "plan", "task", "schedule", "settings", "profile",
  "reminder", "consent", "knowledge_base",
];
const ACTOR_TYPES = ["nutritionist", "client", "agent", "system"];
const PAGE_SIZE = 50;

/**
 * Журнал аудита (P2-8): audit_logs пишется с самого начала (write_audit_log из
 * множества мест — смена статуса, настройки, напоминания, согласие, база знаний…),
 * но пути чтения не было — записи были видны только прямым SQL-запросом к БД.
 */
export function AuditLogPanel() {
  const { t } = useTranslation();
  const [entityType, setEntityType] = useState("");
  const [actorType, setActorType] = useState("");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [hasMore, setHasMore] = useState(true);

  const q = useQuery({
    queryKey: ["audit_logs", entityType, actorType, cursor],
    queryFn: () =>
      api.listAuditLogs({
        entityType: entityType || undefined,
        actorType: actorType || undefined,
        before: cursor,
        limit: PAGE_SIZE,
      }),
  });

  // Курсорная пагинация: новая страница дописывается к уже показанным записям;
  // смена фильтра сбрасывает cursor в undefined, и накопленный список тоже сбрасывается.
  useEffect(() => {
    if (!q.data) return;
    setRows((prev) => (cursor === undefined ? q.data.logs : [...prev, ...q.data.logs]));
    setHasMore(q.data.logs.length === PAGE_SIZE);
  }, [q.data, cursor]);

  const changeFilter = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setCursor(undefined);
    setRows([]);
    setHasMore(true);
  };

  const loadMore = () => {
    if (rows.length === 0) return;
    setCursor(rows[rows.length - 1].timestamp);
  };

  const detail = (row: AuditLogEntry) => {
    const parts: string[] = [];
    if (row.new_value) parts.push(JSON.stringify(row.new_value));
    if (row.old_value) parts.push(`${t("settings.auditLog.was")}: ${JSON.stringify(row.old_value)}`);
    return parts.join(" · ");
  };

  const isFirstLoad = q.isLoading && cursor === undefined;

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">{t("settings.auditLog.hint")}</p>

      <div className="flex flex-wrap gap-2">
        <select
          className="rounded-md border px-2 py-1 text-xs"
          value={entityType}
          onChange={(e) => changeFilter(setEntityType)(e.target.value)}
        >
          <option value="">{t("settings.auditLog.all_entities")}</option>
          {ENTITY_TYPES.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
        <select
          className="rounded-md border px-2 py-1 text-xs"
          value={actorType}
          onChange={(e) => changeFilter(setActorType)(e.target.value)}
        >
          <option value="">{t("settings.auditLog.all_actors")}</option>
          {ACTOR_TYPES.map((v) => (
            <option key={v} value={v}>{v}</option>
          ))}
        </select>
      </div>

      {isFirstLoad && <div className="text-xs text-gray-400">{t("loading")}</div>}
      {q.error && <div className="text-sm text-red-600">{t("settings.auditLog.error")}</div>}

      {!isFirstLoad && rows.length === 0 && !q.error && (
        <div className="py-4 text-center text-xs text-gray-400">{t("settings.auditLog.empty")}</div>
      )}

      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500">
                <th className="py-1 pr-3">{t("settings.auditLog.when")}</th>
                <th className="py-1 pr-3">{t("settings.auditLog.who")}</th>
                <th className="py-1 pr-3">{t("settings.auditLog.action")}</th>
                <th className="py-1 pr-3">{t("settings.auditLog.entity")}</th>
                <th className="py-1">{t("settings.auditLog.details")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t align-top">
                  <td className="py-1.5 pr-3 whitespace-nowrap text-gray-500">{row.timestamp}</td>
                  <td className="py-1.5 pr-3 text-gray-800">{row.actor_name || row.actor_type}</td>
                  <td className="py-1.5 pr-3 text-gray-800">{row.action}</td>
                  <td className="py-1.5 pr-3 text-gray-800">
                    {row.entity_type}
                    {row.entity_name ? ` · ${row.entity_name}` : ""}
                  </td>
                  <td className="py-1.5 text-gray-500 break-all">{detail(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && rows.length > 0 && (
        <Button variant="outline" className="text-xs" disabled={q.isFetching} onClick={loadMore}>
          {q.isFetching ? t("settings.auditLog.loading_more") : t("settings.auditLog.load_more")}
        </Button>
      )}
    </div>
  );
}
