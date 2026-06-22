/**
 * Расчёт срока оплаченного тарифа (clients.paid_until).
 * Используется в реестре (индикатор) и в панели алертов (сигнал за 2 дня).
 */

export type ExpiryKind = "none" | "ok" | "soon" | "expired";

/** Порог «скоро истекает» — за столько дней предупреждаем (по ТЗ — 2 дня). */
export const SOON_DAYS = 2;

/** Полных дней до даты (отрицательное — дата в прошлом). null — дата не задана/некорректна. */
export function daysUntil(dateStr: string | null): number | null {
  if (!dateStr) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}

/** Классификация срока: нет даты / в норме / скоро истекает / истёк. */
export function expiryKind(dateStr: string | null, soonDays = SOON_DAYS): ExpiryKind {
  const d = daysUntil(dateStr);
  if (d === null) return "none";
  if (d < 0) return "expired";
  if (d <= soonDays) return "soon";
  return "ok";
}
