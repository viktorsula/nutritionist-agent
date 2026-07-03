import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api, type ReminderInput } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { useClientReminders, useControlledMetrics } from "./queries";

type Recurrence = "once" | "daily" | "weekly";

/**
 * Редактор напоминаний клиента (Фаза 1). Нутрициолог задаёт текст, время и регулярность;
 * ассистент шлёт их в Telegram по расписанию, несколько на одно время — одним сообщением.
 * Данные идут через бэкенд (таблица под RLS, фронту напрямую недоступна).
 */
export function ReminderEditor({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const reminders = useClientReminders(clientId);
  const metrics = useControlledMetrics(clientId);

  const [title, setTitle] = useState("");
  const [time, setTime] = useState("07:00");
  const [recurrence, setRecurrence] = useState<Recurrence>("daily");
  const [weekday, setWeekday] = useState(0);
  const [date, setDate] = useState("");
  const [needsResponse, setNeedsResponse] = useState(false);
  const [expected, setExpected] = useState("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const weekdays = t("reminders.weekdays", { returnObjects: true }) as string[];
  const catalog = metrics.data ?? [];
  const expectedLabel = (key: string | null): string => {
    if (!key || key === "text") return t("reminders.any_answer");
    return catalog.find((m) => m.key === key)?.label_ru ?? key;
  };
  const invalidate = () => qc.invalidateQueries({ queryKey: ["client_reminders", clientId] });

  async function create(e: FormEvent) {
    e.preventDefault();
    const ttl = title.trim();
    if (!ttl || busy) return;
    setBusy(true);
    setError("");
    const body: ReminderInput = {
      title: ttl,
      remind_at: time,
      recurrence,
      weekday: recurrence === "weekly" ? weekday : null,
      remind_date: recurrence === "once" ? date || null : null,
      requires_response: needsResponse,
      expected_response: needsResponse ? expected : null,
    };
    try {
      await api.createReminder(clientId, body);
      setTitle("");
      setNeedsResponse(false);
      setExpected("text");
      invalidate();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteReminder(clientId, id);
      invalidate();
    } catch {
      /* мягко игнорируем — список обновится */
    }
  }

  function scheduleLabel(r: {
    remind_at: string;
    recurrence: string;
    weekday: number | null;
    remind_date: string | null;
  }): string {
    const at = r.remind_at.slice(0, 5);
    if (r.recurrence === "daily") return `${at} · ${t("reminders.recurrence.daily")}`;
    if (r.recurrence === "weekly")
      return `${at} · ${weekdays[r.weekday ?? 0] ?? ""}`;
    return `${at} · ${t("reminders.on_date")} ${r.remind_date ?? ""}`;
  }

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-gray-700">{t("reminders.heading")}</div>
        <div className="text-xs text-gray-400">{t("reminders.hint")}</div>
      </div>

      {(reminders.data ?? []).length === 0 ? (
        <div className="text-xs text-gray-400">{t("reminders.empty")}</div>
      ) : (
        <ul className="space-y-1">
          {(reminders.data ?? []).map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 flex-1 truncate text-gray-800">
                {r.title}
                <span className="text-gray-400"> · {scheduleLabel(r)}</span>
                {r.requires_response && (
                  <span className="text-amber-600"> · ✋ {expectedLabel(r.expected_response)}</span>
                )}
              </span>
              <button className="text-red-600 hover:underline" onClick={() => remove(r.id)}>
                {t("reminders.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={create} className="space-y-2 border-t pt-3">
        <input
          className={`${input} w-full`}
          placeholder={t("reminders.title")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <div className="flex flex-wrap items-center gap-2">
          <input type="time" className={input} value={time} onChange={(e) => setTime(e.target.value)} />
          <select
            className={input}
            value={recurrence}
            onChange={(e) => setRecurrence(e.target.value as Recurrence)}
          >
            <option value="daily">{t("reminders.recurrence.daily")}</option>
            <option value="weekly">{t("reminders.recurrence.weekly")}</option>
            <option value="once">{t("reminders.recurrence.once")}</option>
          </select>
          {recurrence === "weekly" && (
            <select className={input} value={weekday} onChange={(e) => setWeekday(Number(e.target.value))}>
              {weekdays.map((w, i) => (
                <option key={i} value={i}>
                  {w}
                </option>
              ))}
            </select>
          )}
          {recurrence === "once" && (
            <input type="date" className={input} value={date} onChange={(e) => setDate(e.target.value)} />
          )}
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={needsResponse}
            onChange={(e) => setNeedsResponse(e.target.checked)}
          />
          {t("reminders.needs_response")}
        </label>
        {needsResponse && (
          <label className="flex items-center gap-2 text-xs text-gray-600">
            <span className="text-gray-500">{t("reminders.expected")}</span>
            <select className={input} value={expected} onChange={(e) => setExpected(e.target.value)}>
              <option value="text">{t("reminders.any_answer")}</option>
              {catalog.map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label_ru}
                </option>
              ))}
            </select>
          </label>
        )}
        {error && <div className="text-xs text-red-600">{error}</div>}
        <Button type="submit" disabled={busy}>
          {busy ? t("reminders.adding") : t("reminders.add")}
        </Button>
      </form>
    </div>
  );
}
