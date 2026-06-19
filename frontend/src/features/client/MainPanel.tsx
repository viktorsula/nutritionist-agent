import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { WeightChart, LabChart, CaloriesDynamics, type DailyMacros } from "./charts";
import {
  useClientProfile,
  useMeasurements,
  useLabResults,
  useCalorieEvents,
  type ClientEvent,
} from "./queries";

function numFrom(payload: Record<string, unknown> | null, keys: string[]): number | null {
  if (!payload) return null;
  for (const k of keys) {
    const v = payload[k];
    if (typeof v === "number") return v;
    if (typeof v === "string" && v.trim() && !Number.isNaN(Number(v))) return Number(v);
  }
  return null;
}

/** Агрегирует калории/БЖУ по дням (по возрастанию даты). */
function dailyMacros(events: ClientEvent[]): DailyMacros[] {
  const byDay = new Map<string, DailyMacros>();
  for (const e of events) {
    const day = (e.event_date || "").slice(0, 10);
    if (!day) continue;
    const acc = byDay.get(day) ?? { date: day, kcal: 0, protein: 0, fat: 0, carbs: 0 };
    acc.kcal += numFrom(e.payload_json, ["calories", "kcal"]) ?? 0;
    acc.protein += numFrom(e.payload_json, ["protein", "protein_g"]) ?? 0;
    acc.fat += numFrom(e.payload_json, ["fat", "fat_g"]) ?? 0;
    acc.carbs += numFrom(e.payload_json, ["carbs", "carbohydrates", "carbs_g"]) ?? 0;
    byDay.set(day, acc);
  }
  return Array.from(byDay.values()).sort((a, b) => a.date.localeCompare(b.date));
}

export function MainPanel({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const profile = useClientProfile(clientId);
  const measurements = useMeasurements(clientId);
  const labs = useLabResults(clientId);
  const calories = useCalorieEvents(clientId);

  const daily = dailyMacros(calories.data ?? []);
  const indicators = Array.from(new Set((labs.data ?? []).map((r) => r.indicator)));

  return (
    <div className="space-y-4">
      <Card title={t("client.reminders")}>
        <p className="text-xs text-gray-500">{t("client.reminders_hint")}</p>
      </Card>

      <Card title={t("client.weight_chart")}>
        <WeightChart
          data={measurements.data ?? []}
          target={profile.data?.target_weight}
          emptyText={t("client.no_data")}
        />
      </Card>

      <Card title={t("client.calories")}>
        <CaloriesDynamics
          data={daily}
          emptyText={t("client.calories_empty")}
          kcalLabel={t("client.kcal")}
          proteinLabel={t("client.protein")}
          fatLabel={t("client.fat")}
          carbsLabel={t("client.carbs")}
        />
      </Card>

      <Card title={t("client.labs")}>
        {indicators.length > 0 ? (
          <div className="space-y-4">
            {indicators.map((ind) => (
              <LabChart
                key={ind}
                indicator={ind}
                unit={(labs.data ?? []).find((r) => r.indicator === ind)?.unit ?? null}
                data={(labs.data ?? []).filter((r) => r.indicator === ind)}
              />
            ))}
          </div>
        ) : (
          <div className="py-6 text-center text-xs text-gray-400">{t("client.no_data")}</div>
        )}
      </Card>
    </div>
  );
}
