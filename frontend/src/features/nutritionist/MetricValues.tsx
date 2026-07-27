import { useTranslation } from "react-i18next";
import { useControlledMetrics, useMetricValues } from "./queries";
import type { MetricValue } from "../../lib/api";

/**
 * Значения контролируемых показателей клиента — сон и произвольные (пульс, стресс…),
 * из client_metrics (P2-7).
 *
 * Зачем: нутрициолог настраивает «контролировать пульс», клиент присылает значения,
 * они пишутся в БД — но read-пути наружу не было, и увидеть их было негде. Физические
 * замеры (вес/талия/…) сюда не входят: они лежат в measurements и выводятся графиками.
 */
export function MetricValues({ clientId }: { clientId: string }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language.startsWith("en") ? "en" : "ru";
  const values = useMetricValues(clientId);
  const catalog = useControlledMetrics(clientId);

  if (values.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;
  if (values.error) return <div className="text-sm text-red-600">{t("metrics.values_error")}</div>;

  const rows = values.data ?? [];
  if (rows.length === 0) {
    return <div className="text-xs text-gray-400">{t("metrics.values_empty")}</div>;
  }

  // Человекочитаемое имя и единица — из каталога нутрициолога; если показателя там уже
  // нет (удалён из контроля), показываем сырой ключ, а не прячем накопленные значения.
  const meta = new Map(
    (catalog.data ?? []).map((m) => [
      m.key,
      { label: lang === "en" ? m.label_en || m.label_ru : m.label_ru, unit: m.unit },
    ]),
  );

  // Группируем по показателю, внутри — свежие сверху (бэкенд уже отдал в этом порядке).
  const grouped = new Map<string, MetricValue[]>();
  for (const r of rows) {
    const list = grouped.get(r.metric_key) ?? [];
    list.push(r);
    grouped.set(r.metric_key, list);
  }

  const display = (r: MetricValue, unit?: string) => {
    if (r.value_num !== null && r.value_num !== undefined) {
      return `${r.value_num}${unit ? ` ${unit}` : ""}`;
    }
    return r.value_text || "—";
  };

  // Для сна полезны не только часы, но и во сколько лёг/встал (meta из log_sleep).
  const sleepNote = (r: MetricValue) => {
    const m = r.meta ?? {};
    const bed = m.bedtime as string | undefined;
    const wake = m.wake as string | undefined;
    return bed && wake ? ` (${bed} → ${wake})` : "";
  };

  return (
    <div className="space-y-3">
      {[...grouped.entries()].map(([key, list]) => {
        const info = meta.get(key);
        const unit = info?.unit || list[0]?.unit || "";
        const latest = list[0];
        return (
          <div key={key}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-sm font-medium text-gray-800">{info?.label || key}</span>
              <span className="text-sm text-gray-800">
                {display(latest, unit)}
                {sleepNote(latest)}
              </span>
            </div>
            <div className="mt-0.5 text-[11px] text-gray-400">
              {t("metrics.values_latest")}: {latest.measured_at}
              {list.length > 1 && ` · ${t("metrics.values_records", { n: list.length })}`}
            </div>
            {list.length > 1 && (
              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500">
                {list.slice(1, 8).map((r) => (
                  <span key={r.id}>
                    {r.measured_at}: {display(r, unit)}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
