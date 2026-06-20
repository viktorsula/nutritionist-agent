import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Button } from "../../components/ui/Button";
import { useWellnessRow } from "./queries";

/**
 * Редактор ЗОЖ-плана клиента (сон/активность/восстановление/стресс/заметки).
 * Редактирует последнюю запись wellness_plans (update) либо создаёт первую (insert).
 */
export function WellnessEditor({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const row = useWellnessRow(clientId);

  const [open, setOpen] = useState(false);
  const [f, setF] = useState({
    sleep_target: "",
    activity_target: "",
    recovery: "",
    stress_management: "",
    notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Префилл из текущего плана при открытии формы / смене клиента.
  useEffect(() => {
    const d = row.data;
    setF({
      sleep_target: d?.sleep_target ?? "",
      activity_target: d?.activity_target ?? "",
      recovery: d?.recovery ?? "",
      stress_management: d?.stress_management ?? "",
      notes: d?.notes ?? "",
    });
  }, [row.data, clientId]);

  async function save() {
    setBusy(true);
    setError("");
    const payload = {
      sleep_target: f.sleep_target.trim() || null,
      activity_target: f.activity_target.trim() || null,
      recovery: f.recovery.trim() || null,
      stress_management: f.stress_management.trim() || null,
      notes: f.notes.trim() || null,
    };
    const res = row.data?.id
      ? await supabase.from("wellness_plans").update(payload).eq("id", row.data.id)
      : await supabase.from("wellness_plans").insert({ client_id: clientId, ...payload });
    setBusy(false);
    if (res.error) {
      setError(res.error.message);
      return;
    }
    setOpen(false);
    qc.invalidateQueries({ queryKey: ["wellness_row", clientId] });
    qc.invalidateQueries({ queryKey: ["wellness_plan", clientId] });
  }

  const input = "w-full rounded-md border px-2 py-1 text-sm";
  const Row = ({ label, value }: { label: string; value: string | null }) =>
    value ? (
      <div className="flex justify-between gap-3 text-xs">
        <span className="text-gray-500">{label}</span>
        <span className="text-right text-gray-800">{value}</span>
      </div>
    ) : null;

  return (
    <div className="space-y-2">
      {row.data ? (
        <div className="space-y-1">
          <Row label={t("card.sleep")} value={row.data.sleep_target} />
          <Row label={t("card.activity")} value={row.data.activity_target} />
          <Row label={t("card.recovery")} value={row.data.recovery} />
          <Row label={t("card.stress")} value={row.data.stress_management} />
          <Row label={t("wellness.notes")} value={row.data.notes} />
        </div>
      ) : (
        <div className="text-xs text-gray-400">{t("card.no_data")}</div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-md bg-brand px-3 py-1 text-xs text-white"
      >
        {open ? t("wellness.hide") : t("wellness.edit")}
      </button>

      {open && (
        <div className="space-y-2 border-t pt-2">
          <input
            className={input}
            placeholder={t("card.sleep")}
            value={f.sleep_target}
            onChange={(e) => setF({ ...f, sleep_target: e.target.value })}
          />
          <input
            className={input}
            placeholder={t("card.activity")}
            value={f.activity_target}
            onChange={(e) => setF({ ...f, activity_target: e.target.value })}
          />
          <input
            className={input}
            placeholder={t("card.recovery")}
            value={f.recovery}
            onChange={(e) => setF({ ...f, recovery: e.target.value })}
          />
          <input
            className={input}
            placeholder={t("card.stress")}
            value={f.stress_management}
            onChange={(e) => setF({ ...f, stress_management: e.target.value })}
          />
          <textarea
            className={`${input} h-16 resize-none`}
            placeholder={t("wellness.notes")}
            value={f.notes}
            onChange={(e) => setF({ ...f, notes: e.target.value })}
          />
          {error && <div className="text-xs text-red-600">{error}</div>}
          <Button type="button" onClick={save} disabled={busy}>
            {busy ? t("wellness.saving") : t("wellness.save")}
          </Button>
        </div>
      )}
    </div>
  );
}
