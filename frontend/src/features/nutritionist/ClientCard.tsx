import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { api } from "../../lib/api";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { WeightChart, LabChart, NutritionChart } from "../client/charts";
import {
  useClientProfile,
  useActivePlan,
  useMeasurements,
  useLabResults,
  useNutritionDaily,
} from "../client/queries";
import { useAuditFindings, useClientEventsRecent, useClientRow, useQuestionnaireHistory } from "./queries";
import { NotificationSettings } from "./NotificationSettings";
import { PlanEditor } from "./PlanEditor";
import { WellnessEditor } from "./WellnessEditor";
import { ReportsCard } from "./ReportsCard";
import { StatusEditor } from "./StatusEditor";
import { QuestionnaireView } from "./QuestionnaireView";

function age(birth?: string | null): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const diff = Date.now() - d.getTime();
  return Math.floor(diff / (365.25 * 24 * 3_600_000));
}

const list = (a?: string[] | null) => (a && a.length ? a.join(", ") : null);

function num(v: unknown): number | null {
  if (typeof v === "number") return v;
  if (typeof v === "string" && v.trim() && !Number.isNaN(Number(v))) return Number(v);
  return null;
}

const MEAL_RU: Record<string, string> = {
  breakfast: "Завтрак", lunch: "Обед", dinner: "Ужин", snack: "Перекус", all_day: "За день",
};

/** Человекочитаемое описание события из payload_json (а не сухой event_type). */
function eventLine(e: { event_type: string; payload_json: Record<string, unknown> | null }): string {
  const p = e.payload_json ?? {};
  switch (e.event_type) {
    case "calories_logged": {
      const dish =
        (p.dish_name as string) ||
        ((p.ingredients as string[] | undefined) ?? []).join(", ") ||
        "приём пищи";
      const total = (p.total as Record<string, unknown> | undefined) ?? {};
      const kcal = num(total.kcal);
      const mt = p.meal_type ? `${MEAL_RU[p.meal_type as string] ?? p.meal_type}: ` : "";
      return `${mt}${dish}${kcal ? ` (≈${Math.round(kcal)} ккал)` : ""}`;
    }
    case "water_logged":
      return `Вода: ${num(p.water_ml) ?? "?"} мл`;
    case "weight_logged":
      return `Вес: ${num(p.weight) ?? "?"} кг`;
    case "bad_wellbeing":
      return `Самочувствие: ${(p.reason as string) || "плохое"}`;
    case "wellbeing_logged":
      return `Самочувствие: ${(p.status as string) || "—"}`;
    case "weight_increase":
      return (p.message as string) || `Вес: ${num(p.weight) ?? "?"} кг (рост выше порога)`;
    case "no_response":
      return (p.message as string) || "Клиент не отвечает дольше порога";
    case "meal_not_reported":
    case "reminder_unanswered": {
      const title = (p.title as string) || "";
      const expected = p.expected as string | undefined;
      const expectedLabel = expected ? MEAL_RU[expected] ?? expected : "";
      // title и expectedLabel часто совпадают текстово (напоминание «Обед» → expected
      // meal_type тоже переводится в «Обед») — не дублируем одно и то же слово дважды.
      const showExpected = expectedLabel && expectedLabel.toLowerCase() !== title.toLowerCase();
      const what = e.event_type === "meal_not_reported" ? "Приём пищи не отмечен" : "Напоминание без ответа";
      return [what, title, showExpected ? expectedLabel : ""].filter(Boolean).join(": ");
    }
    case "questionnaire_updated":
      return (p.message as string) || "Клиент обновил анкету онбординга";
    case "plan_exception_claimed": {
      const item = (p.item as string) || "";
      const claim = (p.client_claim as string) || "";
      return ["Клиент заявил об исключении из плана", item, claim].filter(Boolean).join(": ");
    }
    default:
      return e.event_type;
  }
}

/** Карточка клиента для нутрициолога: профиль, планы, задачи, графики, события, заметки.
 *  Грузит строку клиента по clientId — открывается и из реестра, и из чата (Блок 2). */
export function ClientCard({ clientId, onBack }: { clientId: string; onBack: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const lang = i18n.language.startsWith("en") ? "en" : "ru";

  const clientRow = useClientRow(clientId);
  const client = clientRow.data;

  const profile = useClientProfile(clientId);
  const plan = useActivePlan(clientId);
  const measurements = useMeasurements(clientId);
  const labs = useLabResults(clientId);
  const nutrition = useNutritionDaily(clientId);
  const events = useClientEventsRecent(clientId);
  const questionnaireHistory = useQuestionnaireHistory(clientId);
  const [questionnaireVersionId, setQuestionnaireVersionId] = useState("");

  // Находки проактивного аудита клиента (NEW-1) — только открытые, только при находке.
  const auditFindings = useAuditFindings(clientId);
  const [dismissingId, setDismissingId] = useState("");
  const [auditErr, setAuditErr] = useState("");
  async function dismissFinding(findingId: string) {
    setDismissingId(findingId);
    setAuditErr("");
    try {
      await api.dismissAuditFinding(clientId, findingId);
      qc.invalidateQueries({ queryKey: ["audit_findings", clientId] });
    } catch (e) {
      setAuditErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDismissingId("");
    }
  }

  const [notes, setNotes] = useState("");
  const [savingNotes, setSavingNotes] = useState(false);
  const [notesOk, setNotesOk] = useState(false);
  const [alertsOnly, setAlertsOnly] = useState(false);
  useEffect(() => setNotes(client?.nutritionist_notes ?? ""), [clientId, client?.nutritionist_notes]);

  // Анкета: по умолчанию выбрана последняя версия истории (свежая сверху).
  useEffect(() => {
    const list = questionnaireHistory.data ?? [];
    if (!list.some((h) => h.id === questionnaireVersionId)) {
      setQuestionnaireVersionId(list[0]?.id ?? "");
    }
  }, [questionnaireHistory.data, questionnaireVersionId]);

  // Привязка Telegram: создать одноразовую ссылку / отвязать.
  const [tgLink, setTgLink] = useState("");
  const [tgBusy, setTgBusy] = useState(false);
  const [tgCopied, setTgCopied] = useState(false);
  const [tgErr, setTgErr] = useState("");
  useEffect(() => {
    setTgLink("");
    setTgErr("");
    setTgCopied(false);
  }, [clientId]);

  async function createTgLink() {
    if (!window.confirm(t("card.tg_create_confirm"))) return;
    setTgBusy(true);
    setTgErr("");
    setTgCopied(false);
    try {
      const r = await api.telegramLink(clientId);
      setTgLink(r.deep_link || r.token);
      if (!r.configured) setTgErr(t("card.tg_no_username"));
    } catch (e) {
      setTgErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTgBusy(false);
    }
  }

  async function unlinkTg() {
    if (!window.confirm(t("card.tg_unlink_confirm"))) return;
    setTgBusy(true);
    setTgErr("");
    try {
      await api.telegramUnlink(clientId);
      setTgLink("");
      qc.invalidateQueries({ queryKey: ["client_row", clientId] });
    } catch (e) {
      setTgErr(e instanceof Error ? e.message : String(e));
    } finally {
      setTgBusy(false);
    }
  }

  // Сброс пароля клиента: нутрициолог задаёт временный пароль, показывает его (и копирует).
  const [pwBusy, setPwBusy] = useState(false);
  const [pwValue, setPwValue] = useState("");
  const [pwEmailSent, setPwEmailSent] = useState(false);
  const [pwCopied, setPwCopied] = useState(false);
  const [pwErr, setPwErr] = useState("");
  useEffect(() => {
    setPwValue("");
    setPwErr("");
    setPwCopied(false);
    setPwEmailSent(false);
  }, [clientId]);

  async function resetPassword() {
    if (!window.confirm(t("card.pw_reset_confirm"))) return;
    setPwBusy(true);
    setPwErr("");
    setPwCopied(false);
    try {
      const r = await api.resetClientPassword(clientId);
      setPwValue(r.password);
      setPwEmailSent(r.email_sent);
    } catch (e) {
      setPwErr(e instanceof Error ? e.message : String(e));
    } finally {
      setPwBusy(false);
    }
  }

  async function saveNotes() {
    setSavingNotes(true);
    setNotesOk(false);
    const { error } = await supabase
      .from("clients")
      .update({ nutritionist_notes: notes })
      .eq("id", clientId);
    setSavingNotes(false);
    if (!error) {
      setNotesOk(true);
      qc.invalidateQueries({ queryKey: ["registry_clients"] });
      qc.invalidateQueries({ queryKey: ["client_row", clientId] });
    }
  }

  const p = profile.data;
  const tracked = (p?.tracked_lab_indicators ?? [])
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  const Row = ({ label, value }: { label: string; value: ReactNode }) =>
    value ? (
      <div className="flex justify-between gap-3 text-xs">
        <span className="text-gray-500">{label}</span>
        <span className="text-right text-gray-800">{value}</span>
      </div>
    ) : null;

  const badge = (text: string | null) =>
    text ? (
      <span className="rounded-full bg-brand-light px-2 py-0.5 text-[11px] text-brand-dark">
        {text}
      </span>
    ) : null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button onClick={onBack} className="text-sm text-gray-500 hover:text-brand">
            ← {t("card.back")}
          </button>
          <h3 className="text-base font-semibold text-gray-800">
            {client?.name ?? (clientRow.isLoading ? t("loading") : "—")}
          </h3>
        </div>
        <div className="flex flex-wrap gap-1">
          {badge(client?.client_status ? t(`registry.status_value.${client.client_status}`, { defaultValue: client.client_status }) : null)}
          {badge(client?.payment_status ? t(`registry.payment_value.${client.payment_status}`, { defaultValue: client.payment_status }) : null)}
        </div>
      </div>

      {(auditFindings.data?.length ?? 0) > 0 && (
        <Card title={t("card.audit_findings")}>
          {auditErr && <div className="mb-2 text-xs text-red-600">{auditErr}</div>}
          <ul className="space-y-2 text-xs">
            {auditFindings.data!.map((f) => (
              <li
                key={f.id}
                className={`rounded border-l-4 px-2 py-1.5 ${
                  f.severity === "medium"
                    ? "border-l-amber-400 bg-amber-50"
                    : "border-l-gray-300 bg-gray-50"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-gray-800">{f.title}</div>
                    <div className="mt-0.5 text-gray-600">{f.description}</div>
                    <div className="mt-1 text-[10px] text-gray-400">
                      {new Date(f.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 text-gray-400 hover:text-brand disabled:opacity-50"
                    onClick={() => dismissFinding(f.id)}
                    disabled={dismissingId === f.id}
                  >
                    {t("card.audit_dismiss")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card title={t("card.events")}>
        <label className="mb-2 flex items-center gap-2 text-xs text-gray-600">
          <input
            type="checkbox"
            checked={alertsOnly}
            onChange={(e) => setAlertsOnly(e.target.checked)}
          />
          {t("card.alerts_only")}
        </label>
        {(() => {
          const rows = alertsOnly
            ? (events.data ?? []).filter((e) => e.severity)
            : events.data ?? [];
          return rows.length === 0 ? (
            <div className="text-xs text-gray-400">
              {alertsOnly ? t("card.no_alerts") : t("card.no_data")}
            </div>
          ) : (
            <ul className="max-h-[30vh] space-y-1 overflow-y-auto pr-1 text-xs">
              {rows.map((e, i) => {
                const tone =
                  e.severity === "critical"
                    ? "border-l-red-600 bg-red-50"
                    : e.severity === "high"
                      ? "border-l-orange-500 bg-orange-50"
                      : e.severity === "medium"
                        ? "border-l-amber-400 bg-amber-50"
                        : "border-l-transparent";
                const d = new Date(e.event_date);
                return (
                  <li
                    key={i}
                    className={`flex items-start gap-2 rounded border-l-4 px-2 py-1 ${tone}`}
                  >
                    <span className="shrink-0 whitespace-nowrap text-gray-400">
                      {d.toLocaleDateString()}{" "}
                      {d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </span>
                    <span className="text-gray-700">
                      {eventLine(e)}
                      {e.severity ? ` [${e.severity}]` : ""}
                    </span>
                  </li>
                );
              })}
            </ul>
          );
        })()}
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title={t("card.profile_client")}>
          {profile.isLoading ? (
            <div className="text-xs text-gray-400">{t("loading")}</div>
          ) : (
            <div className="space-y-1">
              <Row label={t("card.goal")} value={p?.goals} />
              <Row label={t("card.gender")} value={p?.gender} />
              <Row label={t("card.age")} value={age(p?.birth_date)} />
              <Row
                label={t("card.weight")}
                value={p?.weight != null ? `${p.weight} → ${p?.target_weight ?? "—"} кг` : null}
              />
              <Row label={t("card.activity")} value={p?.activity_level} />
              <Row label={t("card.allergies")} value={list(p?.allergies)} />
              <Row label={t("card.chronic")} value={list(p?.chronic_conditions)} />
              <Row label={t("card.restrictions")} value={list(p?.restrictions)} />
            </div>
          )}

          {/* Полная анкета онбординга — read-only просмотр + история версий (P1-14, миграция 017) */}
          <details className="mt-3 border-t pt-3">
            <summary className="cursor-pointer text-xs font-medium text-gray-600">
              {t("card.questionnaire")}
            </summary>
            <div className="mt-2">
              {(questionnaireHistory.data?.length ?? 0) > 1 && (
                <select
                  className="mb-2 w-full rounded-md border px-2 py-1 text-xs"
                  value={questionnaireVersionId}
                  onChange={(e) => setQuestionnaireVersionId(e.target.value)}
                >
                  {questionnaireHistory.data!.map((h, i) => (
                    <option key={h.id} value={h.id}>
                      {new Date(h.submitted_at).toLocaleString()}
                      {i === 0 ? ` (${t("card.questionnaire_current")})` : ""}
                    </option>
                  ))}
                </select>
              )}
              <QuestionnaireView
                answers={
                  (questionnaireHistory.data?.find((h) => h.id === questionnaireVersionId)
                    ?.questionnaire_json as Record<string, unknown> | undefined) ??
                  (p?.questionnaire_json as Record<string, unknown> | null)
                }
              />
            </div>
          </details>

          {/* Статусы клиента — объединены с профилем */}
          <div className="mt-3 border-t pt-3">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.statuses")}</div>
            <StatusEditor
              clientId={clientId}
              clientStatus={client?.client_status}
              paymentStatus={client?.payment_status}
              paidUntil={client?.paid_until}
            />
          </div>

          {/* Доступ клиента — объединён с профилем */}
          <div className="mt-3 border-t pt-3">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.tg_section")}</div>
            {client?.telegram_id ? (
              <div className="space-y-2">
                <div className="text-xs text-gray-700">
                  {t("card.tg_linked")}: <span className="font-mono">{client.telegram_id}</span>
                </div>
                <Button type="button" onClick={unlinkTg} disabled={tgBusy}>
                  {t("card.tg_unlink")}
                </Button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="text-xs text-gray-500">{t("card.tg_not_linked")}</div>
                <Button type="button" onClick={createTgLink} disabled={tgBusy}>
                  {tgBusy ? t("card.tg_creating") : t("card.tg_create_link")}
                </Button>
                {tgLink && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-gray-500">{t("card.tg_link_hint")}</div>
                    <div className="flex gap-2">
                      <input
                        readOnly
                        value={tgLink}
                        onFocus={(e) => e.currentTarget.select()}
                        className="w-full rounded-md border px-2 py-1 font-mono text-xs"
                      />
                      <Button
                        type="button"
                        onClick={() => {
                          navigator.clipboard?.writeText(tgLink);
                          setTgCopied(true);
                        }}
                      >
                        {tgCopied ? t("card.tg_copied") : t("card.tg_copy")}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {tgErr && <div className="mt-2 text-xs text-red-600">{tgErr}</div>}

            <div className="mt-3 border-t pt-2">
              <div className="mb-1 text-xs font-medium text-gray-600">{t("card.pw_title")}</div>
              <div className="space-y-2">
                <div className="text-[11px] text-gray-500">{t("card.pw_hint")}</div>
                <Button type="button" onClick={resetPassword} disabled={pwBusy}>
                  {pwBusy ? t("card.pw_resetting") : t("card.pw_reset")}
                </Button>
                {pwValue && (
                  <div className="space-y-1">
                    <div className="text-[11px] text-gray-500">{t("card.pw_new")}</div>
                    <div className="flex gap-2">
                      <input
                        readOnly
                        value={pwValue}
                        onFocus={(e) => e.currentTarget.select()}
                        className="w-full rounded-md border px-2 py-1 font-mono text-xs"
                      />
                      <Button
                        type="button"
                        onClick={() => {
                          navigator.clipboard?.writeText(pwValue);
                          setPwCopied(true);
                        }}
                      >
                        {pwCopied ? t("card.pw_copied") : t("card.pw_copy")}
                      </Button>
                    </div>
                    <div className="text-[11px] text-gray-500">
                      {pwEmailSent ? t("card.pw_email_sent") : t("card.pw_email_not_sent")}
                    </div>
                  </div>
                )}
                {pwErr && <div className="mt-2 text-xs text-red-600">{pwErr}</div>}
              </div>
            </div>
          </div>

          {/* Отчёты — объединены с профилем */}
          <div className="mt-3 border-t pt-3">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.reports")}</div>
            <ReportsCard clientId={clientId} />
          </div>
        </Card>

        <Card title={t("card.recommendations")}>
          <div className="mb-1 text-xs font-medium text-gray-600">{t("card.plan")}</div>
          {plan.data ? (
            <div className="space-y-1">
              <Row label={t("card.plan_title")} value={plan.data.title} />
              <Row label={t("card.plan_from")} value={plan.data.effective_from} />
              <Row
                label={t("card.plan_description")}
                value={
                  typeof plan.data.plan_json?.description === "string"
                    ? plan.data.plan_json.description
                    : null
                }
              />
              <Row
                label={t("card.supplements")}
                value={
                  plan.data.supplements_json
                    ? JSON.stringify(plan.data.supplements_json)
                    : null
                }
              />
            </div>
          ) : (
            <div className="text-xs text-gray-400">{t("card.no_plan")}</div>
          )}
          {/* «+новый план» и история — внутри PlanEditor, внизу раздела «План питания» */}
          <div className="mt-2">
            <PlanEditor clientId={clientId} />
          </div>
          <div className="mt-3 border-t pt-2">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.wellness")}</div>
            <WellnessEditor clientId={clientId} />
          </div>
          <div className="mt-3 border-t pt-2">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.notes")}</div>
            <textarea
              className="h-24 w-full resize-none rounded-md border px-3 py-2 text-sm"
              value={notes}
              onChange={(e) => {
                setNotes(e.target.value);
                setNotesOk(false);
              }}
              placeholder={t("card.notes_placeholder")}
            />
            <div className="mt-2 flex items-center gap-2">
              <Button type="button" onClick={saveNotes} disabled={savingNotes}>
                {savingNotes ? t("card.saving") : t("card.save_notes")}
              </Button>
              {notesOk && <span className="text-xs text-green-600">{t("card.saved")}</span>}
            </div>
          </div>
        </Card>

        <div className="lg:col-span-2">
          <Card title={t("card.notifications")}>
            <NotificationSettings clientId={clientId} />
          </Card>
        </div>
      </div>

      <Card title={t("card.weight_chart")}>
        <WeightChart
          data={measurements.data ?? []}
          target={p?.target_weight}
          emptyText={t("card.no_data")}
        />
      </Card>

      <Card title={t("client.calories")}>
        <NutritionChart
          data={nutrition.data?.series ?? []}
          targets={nutrition.data?.targets ?? {}}
          emptyText={t("card.no_data")}
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

      <Card title={t("card.additional")}>
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
                emptyText={t("card.no_data")}
              />
            ))}
          </div>
        ) : (
          <div className="py-4 text-center text-xs text-gray-400">{t("card.no_indicators")}</div>
        )}
      </Card>

    </div>
  );
}
