import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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

export interface DailyMacros {
  date: string;
  kcal: number;
  protein: number;
  fat: number;
  carbs: number;
}

/** Динамика калорий по дням + динамика БЖУ (граммы). */
export function CaloriesDynamics({
  data,
  emptyText,
  kcalLabel,
  proteinLabel,
  fatLabel,
  carbsLabel,
}: {
  data: DailyMacros[];
  emptyText: string;
  kcalLabel: string;
  proteinLabel: string;
  fatLabel: string;
  carbsLabel: string;
}) {
  if (data.length === 0) return empty(emptyText);
  return (
    <div className="space-y-4">
      <div>
        <div className="mb-1 text-xs font-medium text-gray-600">{kcalLabel}</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis fontSize={10} domain={["auto", "auto"]} />
            <Tooltip />
            <Line type="monotone" dataKey="kcal" name={kcalLabel} stroke="#2e7d5b" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div>
        <div className="mb-1 text-xs font-medium text-gray-600">
          {proteinLabel} / {fatLabel} / {carbsLabel}
        </div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis fontSize={10} domain={["auto", "auto"]} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Line type="monotone" dataKey="protein" name={proteinLabel} stroke="#2e7d5b" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="fat" name={fatLabel} stroke="#e67e22" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="carbs" name={carbsLabel} stroke="#2980b9" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** График одного показателя анализов во времени. */
export function LabChart({
  indicator,
  unit,
  data,
}: {
  indicator: string;
  unit: string | null;
  data: LabResult[];
}) {
  const points = data
    .filter((r) => r.value != null)
    .map((r) => ({ date: r.measured_at, value: r.value }));

  return (
    <div>
      <div className="mb-1 text-xs font-medium text-gray-600">
        {indicator}
        {unit ? `, ${unit}` : ""}
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={points} margin={{ top: 4, right: 12, left: -8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
          <XAxis dataKey="date" fontSize={10} />
          <YAxis fontSize={10} domain={["auto", "auto"]} />
          <Tooltip />
          <Line type="monotone" dataKey="value" stroke="#2e7d5b" strokeWidth={2} dot />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
