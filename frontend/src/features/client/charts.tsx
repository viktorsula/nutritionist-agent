import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Measurement, LabResult } from "./queries";

const empty = (text: string) => (
  <div className="py-8 text-center text-xs text-gray-400">{text}</div>
);

/** График динамики веса (+ целевая линия, если задан target_weight). */
export function WeightChart({
  data,
  target,
  emptyText,
}: {
  data: Measurement[];
  target?: number | null;
  emptyText: string;
}) {
  const points = data
    .filter((m) => m.weight != null)
    .map((m) => ({ date: m.measured_at, weight: m.weight }));

  if (points.length === 0) return empty(emptyText);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={points} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
        <XAxis dataKey="date" fontSize={11} />
        <YAxis fontSize={11} domain={["auto", "auto"]} />
        <Tooltip />
        {target != null && (
          <ReferenceLine y={target} stroke="#c0392b" strokeDasharray="4 4" />
        )}
        <Line type="monotone" dataKey="weight" stroke="#2e7d5b" strokeWidth={2} dot />
      </LineChart>
    </ResponsiveContainer>
  );
}

export interface NutritionDay {
  date: string;
  kcal: number;
  protein_g: number;
  fat_g: number;
  carb_g: number;
  sugar_g: number;
  water_ml: number;
}

export interface NutritionLabels {
  nutrition: string;
  kcal: string;
  protein: string;
  fat: string;
  carbs: string;
  sugar: string;
  water: string;
}

/**
 * Графики питания: «Питание» — К/Б/Ж/У + сахар в ОДНОМ поле (две оси: ккал справа,
 * граммы слева, т.к. разный масштаб) с линией целевых калорий; «Вода» — отдельно, с
 * линией нормы. Нормы (targets) приходят из активного плана.
 */
export function NutritionChart({
  data,
  targets,
  emptyText,
  labels,
}: {
  data: NutritionDay[];
  targets: { kcal?: number; water_ml?: number };
  emptyText: string;
  labels: NutritionLabels;
}) {
  if (data.length === 0) return empty(emptyText);
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 text-xs font-medium text-gray-600">{labels.nutrition}</div>
        <ResponsiveContainer width="100%" height={210}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis yAxisId="g" fontSize={10} domain={[0, "auto"]} />
            <YAxis yAxisId="kcal" orientation="right" fontSize={10} domain={[0, "auto"]} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {targets.kcal ? (
              <ReferenceLine yAxisId="kcal" y={targets.kcal} stroke="#c0392b" strokeDasharray="4 4" />
            ) : null}
            <Line yAxisId="kcal" type="monotone" dataKey="kcal" name={labels.kcal} stroke="#2e7d5b" strokeWidth={2} dot />
            <Line yAxisId="g" type="monotone" dataKey="protein_g" name={labels.protein} stroke="#8e44ad" strokeWidth={2} dot={false} />
            <Line yAxisId="g" type="monotone" dataKey="fat_g" name={labels.fat} stroke="#e67e22" strokeWidth={2} dot={false} />
            <Line yAxisId="g" type="monotone" dataKey="carb_g" name={labels.carbs} stroke="#2980b9" strokeWidth={2} dot={false} />
            <Line yAxisId="g" type="monotone" dataKey="sugar_g" name={labels.sugar} stroke="#c0392b" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div>
        <div className="mb-1 text-xs font-medium text-gray-600">{labels.water}</div>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis fontSize={10} domain={[0, "auto"]} />
            <Tooltip />
            {targets.water_ml ? (
              <ReferenceLine y={targets.water_ml} stroke="#c0392b" strokeDasharray="4 4" />
            ) : null}
            <Line type="monotone" dataKey="water_ml" name={labels.water} stroke="#2980b9" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/**
 * График одного показателя анализов во времени.
 * label — отображаемое имя (если не задано — indicator/key).
 * refMin/refMax — полоса нормы (если заданы), задаёт нутрициолог.
 * emptyText — текст-плейсхолдер, если показатель выбран, но данных ещё нет.
 */
export function LabChart({
  indicator,
  label,
  unit,
  data,
  refMin,
  refMax,
  emptyText,
}: {
  indicator: string;
  label?: string | null;
  unit: string | null;
  data: LabResult[];
  refMin?: number | null;
  refMax?: number | null;
  emptyText?: string;
}) {
  const points = data
    .filter((r) => r.value != null)
    .map((r) => ({ date: r.measured_at, value: r.value }));

  const title = (
    <div className="mb-1 text-xs font-medium text-gray-600">
      {label || indicator}
      {unit ? `, ${unit}` : ""}
      {refMin != null && refMax != null && (
        <span className="ml-1 text-gray-400">(норма {refMin}–{refMax})</span>
      )}
    </div>
  );

  if (points.length === 0) {
    return (
      <div>
        {title}
        {empty(emptyText ?? "Нет данных")}
      </div>
    );
  }

  return (
    <div>
      {title}
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={points} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="date" fontSize={10} />
          <YAxis fontSize={10} domain={["auto", "auto"]} />
          <Tooltip />
          {refMin != null && refMax != null && (
            <ReferenceArea y1={refMin} y2={refMax} fill="#2e7d5b" fillOpacity={0.08} />
          )}
          <Line type="monotone" dataKey="value" stroke="#2e7d5b" strokeWidth={2} dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
