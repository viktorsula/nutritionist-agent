import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import { WeightChart, LabChart } from "../client/charts";
import {
  useClientProfile,
  useActivePlan,
  useWellnessPlan,
  useMeasurements,
  useLabResults,
} from "../client/queries";
import { useClientTasks, useClientEventsRecent, type RegistryRow } from "./queries";

function age(birth?: string | null): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const diff = Date.now() - d.getTime();
  return Math.floor(diff / (365.25 * 24 * 3_600_000));
}

const list = (a?: string[] | null) => (a && a.length ? a.join(", ") : null);

/** Карточка клиента для нутрициолога: профиль, планы, задачи, графики, события, заметки. */
export function ClientCard({ client, onBack }: { client: RegistryRow; onBack: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const clientId = client.id;
  const lang = i18n.language.startsWith("en") ? "en" : "ru";

  const profile = useClientProfile(clientId);
  const plan = useActivePlan(clientId);
  const wellness = useWellnessPlan(clientId);
  const measurements = useMeasurements(clientId);
  const labs = useLabResults(clientId);
  const tasks = useClientTasks(clientId);
  const events = useClientEventsRecent(clientId);

  const [notes, setNotes] = useState(client.nutritionist_notes ?? "");
  const [savingNotes, setSavingNotes] = useState(false);
  const [notesOk, setNotesOk] = useState(false);
  useEffect(() => setNotes(client.nutritionist_notes ?? ""), [client.id, client.nutritionist_notes]);

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
          <h3 className="text-base font-semibold text-gray-800">{client.name}</h3>
        </div>
        <div className="flex flex-wrap gap-1">
          {badge(client.client_status)}
          {badge(client.payment_status)}
          {badge(client.access_status)}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card title={t("card.profile")}>
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
        </Card>

        <Card title={t("card.plan")}>
          {plan.data ? (
            <div className="space-y-1">
              <Row label={t("card.plan_title")} value={plan.data.title} />
              <Row label={t("card.plan_from")} value={plan.data.effective_from} />
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
          <div className="mt-3 border-t pt-2">
            <div className="mb-1 text-xs font-medium text-gray-600">{t("card.wellness")}</div>
            {wellness.data ? (
              <div className="space-y-1">
                <Row label={t("card.sleep")} value={wellness.data.sleep_target} />
                <Row label={t("card.activity")} value={wellness.data.activity_target} />
                <Row label={t("card.recovery")} value={wellness.data.recovery} />
                <Row label={t("card.stress")} value={wellness.data.stress_management} />
              </div>
            ) : (
              <div className="text-xs text-gray-400">{t("card.no_data")}</div>
            )}
          </div>
        </Card>

        <Card title={t("card.tasks")}>
          {(tasks.data ?? []).length === 0 ? (
            <div className="text-xs text-gray-400">{t("card.no_tasks")}</div>
          ) : (
            <ul className="space-y-1">
              {(tasks.data ?? []).map((tk) => (
                <li key={tk.id} className="flex justify-between gap-2 text-xs">
                  <span className="text-gray-800">{tk.title}</span>
                  <span className="text-gray-400">
                    {tk.status}
                    {tk.due_date ? ` · ${tk.due_date.slice(0, 10)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={t("card.notes")}>
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
        </Card>
      </div>

      <Card title={t("card.weight_chart")}>
        <WeightChart
          data={measurements.data ?? []}
          target={p?.target_weight}
          emptyText={t("card.no_data")}
        />
      </Card>

      <Card title={t("card.labs")}>
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

      <Card title={t("card.events")}>
        {(events.data ?? []).length === 0 ? (
          <div className="text-xs text-gray-400">{t("card.no_data")}</div>
        ) : (
          <ul className="space-y-1 text-xs">
            {(events.data ?? []).map((e, i) => (
              <li key={i} className="flex justify-between gap-2">
                <span className="text-gray-700">
                  {e.event_type}
                  {e.severity ? ` [${e.severity}]` : ""}
                </span>
                <span className="text-gray-400">{new Date(e.event_date).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
