import {
  CartesianGrid,
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

/** Один маленький график метрики питания (для сетки 2-в-ряд). */
function NutritionMini({
  data,
  dataKey,
  title,
  color,
  target,
}: {
  data: NutritionDay[];
  dataKey: keyof NutritionDay;
  title: string;
  color: string;
  target?: number;
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium text-gray-600">{title}</div>
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={data} margin={{ top: 4, right: 10, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="date" fontSize={9} />
          <YAxis fontSize={9} domain={[0, "auto"]} />
          <Tooltip />
          {target ? <ReferenceLine y={target} stroke="#c0392b" strokeDasharray="4 4" /> : null}
          <Line type="monotone" dataKey={dataKey as string} name={title} stroke={color} strokeWidth={2} dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/**
 * Графики питания: 6 отдельных графиков (ккал/белки/жиры/углеводы/сахар/вода), по 2 в ряд.
 * Нормы (целевые калории, норма воды) из активного плана — линией на соответствующих графиках.
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
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <NutritionMini data={data} dataKey="kcal" title={labels.kcal} color="#2e7d5b" target={targets.kcal} />
      <NutritionMini data={data} dataKey="water_ml" title={labels.water} color="#2980b9" target={targets.water_ml} />
      <NutritionMini data={data} dataKey="protein_g" title={labels.protein} color="#8e44ad" />
      <NutritionMini data={data} dataKey="fat_g" title={labels.fat} color="#e67e22" />
      <NutritionMini data={data} dataKey="carb_g" title={labels.carbs} color="#2980b9" />
      <NutritionMini data={data} dataKey="sugar_g" title={labels.sugar} color="#c0392b" />
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
