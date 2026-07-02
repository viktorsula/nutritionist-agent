import { useTranslation } from "react-i18next";
import { Card } from "../../components/ui/Card";
import { WeightChart, LabChart, NutritionChart } from "./charts";
import {
  useClientProfile,
  useMeasurements,
  useLabResults,
  useNutritionDaily,
} from "./queries";

export function MainPanel({ clientId }: { clientId: string }) {
  const { t, i18n } = useTranslation();
  const profile = useClientProfile(clientId);
  const measurements = useMeasurements(clientId);
  const labs = useLabResults(clientId);
  const nutrition = useNutritionDaily(clientId);

  const lang = i18n.language.startsWith("en") ? "en" : "ru";

  // Показатели для графика: если нутрициолог выбрал список — рисуем строго его
  // (в порядке order, с нормой и плейсхолдером «нет данных»). Иначе — все, по
  // которым есть данные (обратная совместимость до настройки нутрициологом).
  const tracked = (profile.data?.tracked_lab_indicators ?? [])
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  const fallbackKeys = Array.from(new Set((labs.data ?? []).map((r) => r.indicator)));

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
        <NutritionChart
          data={nutrition.data?.series ?? []}
          targets={nutrition.data?.targets ?? {}}
          emptyText={t("client.calories_empty")}
          labels={{
            nutrition: t("client.nutrition_macros"),
            kcal: t("client.kcal"),
            protein: t("client.protein"),
            fat: t("client.fat"),
            carbs: t("client.carbs"),
            sugar: t("client.sugar"),
            water: t("client.water"),
          }}
        />
      </Card>

      <Card title={t("client.labs")}>
        {tracked.length > 0 ? (
          <div className="space-y-4">
            {tracked.map((ind) => (
              <LabChart
                key={ind.key}
                indicator={ind.key}
                label={lang === "en" ? ind.label_en : ind.label_ru}
                unit={ind.unit}
                refMin={ind.ref_min}
                refMax={ind.ref_max}
                data={(labs.data ?? []).filter((r) => r.indicator === ind.key)}
                emptyText={t("client.no_data")}
              />
            ))}
          </div>
        ) : fallbackKeys.length > 0 ? (
          <div className="space-y-4">
            {fallbackKeys.map((ind) => (
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
