import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/Button";

/**
 * Покрытие ходов LLM-оркестраторами (P2-14): доля ходов, обработанных оркестратором,
 * и число откатов на старый граф LangGraph.
 *
 * Зачем нутрициологу: это индикатор здоровья основного пути. Откаты (graph_fallback)
 * означают, что оркестратор упал и ход доработал граф — ответ клиент получил, но
 * инструменты записи данных могли не сработать. Роут существовал давно, но не был
 * выведен в интерфейс, поэтому эти сбои никто не видел.
 */
export function CoveragePanel() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["coverage"], queryFn: api.coverage });

  if (q.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;
  if (q.error) return <div className="text-sm text-red-600">{t("settings.coverage.error")}</div>;

  const data = q.data;
  const counts = data?.counts ?? {};
  const hasData = Object.keys(counts).length > 0;

  const pct = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

  const rows: { role: "client" | "nutritionist"; label: string }[] = [
    { role: "client", label: t("settings.coverage.role_client") },
    { role: "nutritionist", label: t("settings.coverage.role_nutritionist") },
  ];

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">{t("settings.coverage.hint")}</p>

      {!hasData ? (
        <div className="py-4 text-center text-xs text-gray-400">
          {t("settings.coverage.empty")}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500">
                <th className="py-1 pr-3">{t("settings.coverage.role")}</th>
                <th className="py-1 pr-3">{t("settings.coverage.rate")}</th>
                <th className="py-1">{t("settings.coverage.fallbacks")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ role, label }) => {
                const fallbacks = data?.fallbacks?.[role] ?? 0;
                return (
                  <tr key={role} className="border-t">
                    <td className="py-1.5 pr-3 text-gray-800">{label}</td>
                    <td className="py-1.5 pr-3 text-gray-800">
                      {pct(data?.orchestrator_rate?.[role])}
                    </td>
                    <td
                      className={`py-1.5 ${fallbacks > 0 ? "font-medium text-orange-600" : "text-gray-500"}`}
                    >
                      {fallbacks}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Button variant="outline" onClick={() => q.refetch()}>
        {t("settings.coverage.refresh")}
      </Button>
    </div>
  );
}
