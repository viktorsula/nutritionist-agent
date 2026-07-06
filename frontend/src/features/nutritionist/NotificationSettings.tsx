import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api, type Reminder, type ReminderInput, type ControlledMetric } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { useClientReminders, useControlledMetrics } from "./queries";

type Category = "physical" | "sleep" | "water" | "meal" | "custom";
type Recurrence = "daily" | "weekly" | "once";

/** Дедлайны отчёта по приёмам пищи (локальное время). Пропуск к дедлайну → алерт нутрициологу. */
const MEAL_DEADLINE: Record<string, string> = {
  breakfast: "12:00",
  lunch: "17:00",
  dinner: "22:00",
};

interface Preset {
  key: string; // ключ показателя / meal_type
  category: Category;
  unit: string;
}

// Порядок в выпадающем списке. «Свой показатель» добавляется отдельным пунктом в конце.
const PRESETS: Preset[] = [
  { key: "weight", category: "physical", unit: "кг" },
  { key: "sleep", category: "sleep", unit: "ч" },
  { key: "water", category: "water", unit: "мл" },
  { key: "breakfast", category: "meal", unit: "" },
  { key: "lunch", category: "meal", unit: "" },
  { key: "dinner", category: "meal", unit: "" },
  { key: "waist", category: "physical", unit: "см" },
  { key: "hips", category: "physical", unit: "см" },
  { key: "neck", category: "physical", unit: "см" },
  { key: "chest", category: "physical", unit: "см" },
];

/** Черновик строки — одно напоминание (`reminders`) плюс метаданные для отрисовки. */
interface Row {
  uid: string; // локальный ключ строки
  id?: string; // reminder.id, если уже сохранён
  title: string;
  metricKey: string; // ключ для expected_response (или 'text' для произвольного)
  category: Category;
  unit: string;
  time: string; // 'HH:MM'
  recurrence: Recurrence;
  weekday: number; // 0=Пн … 6=Вс
  date: string; // 'YYYY-MM-DD'
  awaitResponse: boolean;
  retryCount: number; // max_followups
}

let _uid = 0;
const nextUid = () => `r${++_uid}`;

function categoryOf(expected: string | null | undefined): Category {
  if (!expected || expected === "text") return "custom";
  if (expected in MEAL_DEADLINE) return "meal";
  if (expected === "water") return "water";
  if (expected === "sleep") return "sleep";
  if (["weight", "waist", "hips", "neck", "chest"].includes(expected)) return "physical";
  return "custom";
}

function slug(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "_");
}

const timeShort = (t: string) => (t || "").slice(0, 5);

function reminderToRow(r: Reminder): Row {
  return {
    uid: nextUid(),
    id: r.id,
    title: r.title,
    metricKey: r.expected_response || (r.requires_response ? "text" : ""),
    category: categoryOf(r.expected_response),
    unit: "",
    time: timeShort(r.remind_at),
    recurrence: (r.recurrence as Recurrence) || "daily",
    weekday: r.weekday ?? 0,
    date: r.remind_date || "",
    awaitResponse: r.requires_response,
    retryCount: r.max_followups ?? 3,
  };
}

/** Полезная нагрузка напоминания из строки черновика (маппинг row → reminders). */
function rowToInput(row: Row): ReminderInput {
  const awaiting = row.awaitResponse;
  return {
    title: row.title.trim(),
    remind_at: row.time,
    recurrence: row.recurrence,
    weekday: row.recurrence === "weekly" ? row.weekday : null,
    remind_date: row.recurrence === "once" ? row.date || null : null,
    requires_response: awaiting,
    expected_response: awaiting ? row.metricKey || "text" : null,
    // Еда: жёсткий дедлайн отчёта (12/17/22) активирует контроль пропуска приёма пищи.
    response_deadline: awaiting && row.category === "meal" ? MEAL_DEADLINE[row.metricKey] ?? null : null,
    max_followups: awaiting ? row.retryCount : null,
    followup_after_hours: null,
  };
}

/** Сравнение строки с сохранённым напоминанием — нужно ли слать PATCH. */
function changed(row: Row, r: Reminder): boolean {
  const a = rowToInput(row);
  return (
    a.title !== r.title ||
    a.remind_at !== timeShort(r.remind_at) ||
    a.recurrence !== r.recurrence ||
    (a.weekday ?? null) !== (r.weekday ?? null) ||
    (a.remind_date ?? null) !== (r.remind_date ?? null) ||
    a.requires_response !== r.requires_response ||
    (a.expected_response ?? null) !== (r.expected_response ?? null) ||
    (a.response_deadline ?? null) !== (r.response_deadline ?? null) ||
    (a.max_followups ?? null) !== (r.max_followups ?? null)
  );
}

// ── иконки по смыслу ────────────────────────────────────────────────────────
function iconPath(category: Category, name: string): string {
  if (category === "sleep") return "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z";
  if (category === "water") return "M12 3s6 6.3 6 10.5a6 6 0 0 1-12 0C6 9.3 12 3 12 3z";
  if (category === "meal") return "M3 11h18a9 9 0 0 1-18 0zM12 11V4M9 6c0-1.5 6-1.5 6 0";
  if (category === "physical") {
    if (name.toLowerCase().includes("вес") || name.toLowerCase().includes("weight"))
      return "M12 3v3M6 6h12M6 6l-3 7a3 3 0 0 0 6 0L6 6zm12 0l-3 7a3 3 0 0 0 6 0l-3-7zM9 21h6M12 6v15";
    return "M15.7 3.3l5 5a1 1 0 0 1 0 1.4L9.7 20.7a1 1 0 0 1-1.4 0l-5-5a1 1 0 0 1 0-1.4L14.3 3.3a1 1 0 0 1 1.4 0zM8 8l2 2M11 5l2 2M5 11l2 2";
  }
  const n = name.toLowerCase();
  if (/давлен|пульс|сердц|pressure|heart/.test(n)) return "M12 21s-7-4.5-9.5-9A5 5 0 0 1 12 6a5 5 0 0 1 9.5 6c-2.5 4.5-9.5 9-9.5 9z";
  if (/актив|шаг|трениров|activity|steps/.test(n)) return "M3 12h4l3 8 4-16 3 8h4";
  return "M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0l-7-7A2 2 0 0 1 3 12V5a2 2 0 0 1 2-2h7a2 2 0 0 1 1.4.6l7.2 7.2a2 2 0 0 1 0 2.6z";
}

function Icon({ category, name }: { category: Category; name: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round">
      <path d={iconPath(category, name)} />
    </svg>
  );
}

/**
 * Настройка уведомлений (замена «Задачи и заметки»). Нутрициолог собирает список показателей,
 * о которых напоминать/что контролировать; каждая строка — напоминание (`reminders`).
 * Ассистент шлёт всё одним Telegram-сообщением по расписанию и сам пишет тёплый текст.
 */
export function NotificationSettings({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const reminders = useClientReminders(clientId);
  const catalog = useControlledMetrics(clientId);

  const [rows, setRows] = useState<Row[]>([]);
  const [picker, setPicker] = useState(""); // выбранный пункт списка добавления
  const [customName, setCustomName] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState("");

  const serverRows = useMemo(() => reminders.data ?? [], [reminders.data]);
  useEffect(() => {
    setRows(serverRows.map(reminderToRow));
    setOk(false);
  }, [serverRows]);

  const weekdays = t("notif.weekdays", { returnObjects: true }) as string[];
  const presetLabel = (key: string) => t(`notif.preset.${key}`, { defaultValue: key });

  function dirtyReset() {
    setOk(false);
    setError("");
  }

  function addRow() {
    const isCustom = picker === "__custom__";
    const name = isCustom ? customName.trim() : picker;
    if (!name) return;
    const preset = PRESETS.find((p) => p.key === picker);
    const row: Row = {
      uid: nextUid(),
      title: isCustom ? name : presetLabel(preset!.key),
      metricKey: isCustom ? slug(name) : preset!.key,
      category: isCustom ? "custom" : preset!.category,
      unit: isCustom ? "" : preset!.unit,
      time: "08:00",
      recurrence: "daily",
      weekday: 0,
      date: "",
      awaitResponse: true,
      retryCount: 3,
    };
    setRows([...rows, row]);
    setPicker("");
    setCustomName("");
    dirtyReset();
  }

  function patch(uid: string, patch: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.uid === uid ? { ...r, ...patch } : r)));
    dirtyReset();
  }

  function removeRow(uid: string) {
    setRows((rs) => rs.filter((r) => r.uid !== uid));
    dirtyReset();
  }

  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const byId = new Map(serverRows.map((r) => [r.id, r]));
      const keepIds = new Set(rows.filter((r) => r.id).map((r) => r.id!));

      // Удалить снятые строки.
      for (const r of serverRows) {
        if (!keepIds.has(r.id)) await api.deleteReminder(clientId, r.id);
      }
      // Создать новые / обновить изменённые.
      for (const row of rows) {
        if (!row.title.trim()) continue;
        const body = rowToInput(row);
        if (!row.id) {
          await api.createReminder(clientId, body);
        } else if (changed(row, byId.get(row.id)!)) {
          await api.updateReminder(clientId, row.id, body);
        }
      }
      // Синхронизировать каталог контролируемых показателей произвольными строками
      // (чтобы ассистент знал ключ и сохранял динамику — детерминированный детект).
      const existing = catalog.data ?? [];
      const known = new Set(existing.map((m) => m.key));
      const customs: ControlledMetric[] = rows
        .filter((r) => r.category === "custom" && r.awaitResponse && r.metricKey && !known.has(r.metricKey))
        .map((r) => ({ key: r.metricKey, label_ru: r.title.trim(), unit: r.unit, category: "custom" }));
      if (customs.length) {
        await api.setControlledMetrics(clientId, [...existing, ...customs]);
        qc.invalidateQueries({ queryKey: ["controlled_metrics", clientId] });
      }

      qc.invalidateQueries({ queryKey: ["client_reminders", clientId] });
      setOk(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    setRows(serverRows.map(reminderToRow));
    dirtyReset();
  }

  const input = "rounded-md border px-2 py-1 text-sm";
  const hasMeasures = rows.some((r) => r.category === "meal");

  return (
    <div className="space-y-3">
      <div>
        <div className="text-sm font-medium text-gray-700">{t("notif.heading")}</div>
        <div className="text-xs text-gray-400">{t("notif.subtitle")}</div>
      </div>

      {/* Строка добавления */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border bg-gray-50 p-2">
        <select
          className={`${input} min-w-[200px] flex-1`}
          value={picker}
          onChange={(e) => setPicker(e.target.value)}
        >
          <option value="" disabled>
            {t("notif.pick_placeholder")}
          </option>
          {PRESETS.map((p) => (
            <option key={p.key} value={p.key}>
              {presetLabel(p.key)}
            </option>
          ))}
          <option disabled>──────────</option>
          <option value="__custom__">{t("notif.custom_option")}</option>
        </select>
        {picker === "__custom__" && (
          <input
            className={`${input} min-w-[180px] flex-1`}
            placeholder={t("notif.custom_placeholder")}
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addRow()}
          />
        )}
        <Button type="button" onClick={addRow}>
          {t("notif.add")}
        </Button>
      </div>

      {/* Таблица показателей */}
      {rows.length === 0 ? (
        <div className="rounded-md border border-dashed py-8 text-center text-xs text-gray-400">
          {t("notif.empty")}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[720px] text-xs">
            <thead>
              <tr className="border-b bg-gray-50 text-left text-gray-500">
                <th className="px-2 py-2 font-medium">{t("notif.col_metric")}</th>
                <th className="px-2 py-2 font-medium">{t("notif.col_time")}</th>
                <th className="px-2 py-2 font-medium">{t("notif.col_recurrence")}</th>
                <th className="px-2 py-2 text-center font-medium">{t("notif.col_await")}</th>
                <th className="px-2 py-2 text-center font-medium" title={t("notif.col_repeats_hint")}>
                  {t("notif.col_repeats")}
                </th>
                <th className="w-8 px-2 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.uid} className="border-b last:border-b-0">
                  <td className="px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded bg-gray-100 text-brand-dark">
                        <Icon category={r.category} name={r.title} />
                      </span>
                      <input
                        className="w-full rounded border border-transparent px-1.5 py-1 font-medium hover:border-gray-200 focus:border-brand focus:outline-none"
                        value={r.title}
                        onChange={(e) => patch(r.uid, { title: e.target.value })}
                      />
                    </div>
                  </td>
                  <td className="px-2 py-1.5">
                    <input
                      type="time"
                      className={`${input} w-[92px]`}
                      value={r.time}
                      onChange={(e) => patch(r.uid, { time: e.target.value })}
                    />
                  </td>
                  <td className="px-2 py-1.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <select
                        className={input}
                        value={r.recurrence}
                        onChange={(e) => patch(r.uid, { recurrence: e.target.value as Recurrence })}
                      >
                        <option value="daily">{t("notif.recurrence.daily")}</option>
                        <option value="weekly">{t("notif.recurrence.weekly")}</option>
                        <option value="once">{t("notif.recurrence.once")}</option>
                      </select>
                      {r.recurrence === "weekly" && (
                        <select
                          className={input}
                          value={r.weekday}
                          onChange={(e) => patch(r.uid, { weekday: Number(e.target.value) })}
                        >
                          {weekdays.map((w, i) => (
                            <option key={i} value={i}>
                              {w}
                            </option>
                          ))}
                        </select>
                      )}
                      {r.recurrence === "once" && (
                        <input
                          type="date"
                          className={input}
                          value={r.date}
                          onChange={(e) => patch(r.uid, { date: e.target.value })}
                        />
                      )}
                    </div>
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand"
                      checked={r.awaitResponse}
                      onChange={(e) => patch(r.uid, { awaitResponse: e.target.checked })}
                      aria-label={t("notif.col_await")}
                    />
                  </td>
                  <td className={`px-2 py-1.5 text-center ${r.awaitResponse ? "" : "opacity-35"}`}>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      className={`${input} w-16 text-center`}
                      value={r.retryCount}
                      disabled={!r.awaitResponse}
                      onChange={(e) => patch(r.uid, { retryCount: Number(e.target.value) })}
                    />
                  </td>
                  <td className="px-2 py-1.5 text-center">
                    <button
                      type="button"
                      onClick={() => removeRow(r.uid)}
                      className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-600"
                      title={t("notif.delete")}
                    >
                      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6M10 11v6M14 11v6" />
                      </svg>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Как формируется сообщение — вместо предпросмотра */}
      <div className="flex items-start gap-2 rounded-md border border-brand-light bg-brand-light/40 px-3 py-2 text-xs text-gray-600">
        <svg viewBox="0 0 24 24" className="mt-0.5 h-4 w-4 shrink-0 text-brand-dark" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 16v-4M12 8h.01" />
        </svg>
        <span>{hasMeasures ? t("notif.compose_note_meals") : t("notif.compose_note")}</span>
      </div>

      {error && <div className="text-xs text-red-600">{error}</div>}
      <div className="flex items-center gap-2">
        <Button type="button" onClick={save} disabled={busy}>
          {busy ? t("notif.saving") : t("notif.save")}
        </Button>
        <button type="button" onClick={cancel} className="text-xs text-gray-500 hover:underline" disabled={busy}>
          {t("notif.cancel")}
        </button>
        {ok && <span className="text-xs text-green-600">{t("notif.saved")}</span>}
      </div>
    </div>
  );
}
