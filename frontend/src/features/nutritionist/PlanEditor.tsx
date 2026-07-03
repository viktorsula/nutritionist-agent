import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Button } from "../../components/ui/Button";
import { useClientPlans } from "./queries";

const today = () => new Date().toISOString().slice(0, 10);
const splitList = (s: string) =>
  s.split(",").map((x) => x.trim()).filter(Boolean);

/** Редактор планов питания: история версий + создание нового активного плана. */
export function PlanEditor({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const plans = useClientPlans(clientId);

  const [selectedId, setSelectedId] = useState("");
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [effFrom, setEffFrom] = useState(today());
  const [calories, setCalories] = useState("");
  const [restrictions, setRestrictions] = useState("");
  const [supplements, setSupplements] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const list = plans.data ?? [];
  // По умолчанию показываем активную версию (иначе самую свежую).
  useEffect(() => {
    if (list.length === 0) return;
    if (!list.some((p) => p.id === selectedId)) {
      setSelectedId((list.find((p) => p.is_active) ?? list[0]).id);
    }
  }, [list, selectedId]);
  const selected = list.find((p) => p.id === selectedId) ?? null;

  async function create(e: FormEvent) {
    e.preventDefault();
    const ttl = title.trim();
    if (!ttl || busy) return;
    setBusy(true);
    setError("");
    try {
      // 1. Деактивируем текущий активный план ДО вставки нового
      //    (EXCLUDE-constraint допускает только один активный; триггер деактивации
      //    срабатывает AFTER INSERT — слишком поздно, делаем сами заранее).
      const deact = await supabase
        .from("nutrition_plans")
        .update({ is_active: false, effective_to: effFrom })
        .eq("client_id", clientId)
        .eq("is_active", true);
      if (deact.error) throw deact.error;

      // 2. Вставляем новый активный план (version проставит триггер).
      const ins = await supabase.from("nutrition_plans").insert({
        client_id: clientId,
        title: ttl,
        created_by: "nutritionist",
        effective_from: effFrom,
        is_active: true,
        plan_json: {
          description: description.trim() || null,
          target_calories: calories.trim() ? Number(calories) : null,
          restrictions: splitList(restrictions),
        },
        supplements_json: { items: splitList(supplements) },
      });
      if (ins.error) throw ins.error;

      setTitle("");
      setCalories("");
      setRestrictions("");
      setSupplements("");
      setDescription("");
      setOpen(false);
      setSelectedId(""); // после обновления списка эффект выберет новый активный план
      qc.invalidateQueries({ queryKey: ["client_plans", clientId] });
      qc.invalidateQueries({ queryKey: ["active_plan", clientId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("plan.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      {list.length === 0 ? (
        <div className="text-xs text-gray-400">{t("plan.none")}</div>
      ) : (
        <div className="space-y-2">
          <label className="flex w-full items-center gap-2 text-xs text-gray-600">
            <span className="shrink-0 text-gray-500">{t("plan.history")}</span>
            <select
              className="min-w-0 flex-1 truncate rounded-md border px-2 py-1 text-xs"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {list.map((pl) => (
                <option key={pl.id} value={pl.id}>
                  v{pl.version}. {pl.title}
                  {pl.is_active ? ` · ${t("plan.active")}` : ""}
                </option>
              ))}
            </select>
          </label>

          {selected && (
            <div className="space-y-1 rounded-md border bg-gray-50 px-3 py-2 text-xs">
              <div className="text-gray-400">
                {selected.effective_from}
                {selected.effective_to ? ` – ${selected.effective_to}` : ""}
                {selected.is_active ? ` · ${t("plan.active")}` : ""}
              </div>
              {selected.plan_json?.target_calories != null && (
                <div>
                  <span className="text-gray-500">{t("plan.calories")}:</span>{" "}
                  {selected.plan_json.target_calories}
                </div>
              )}
              {(selected.plan_json?.restrictions?.length ?? 0) > 0 && (
                <div>
                  <span className="text-gray-500">{t("plan.restrictions_label")}:</span>{" "}
                  {selected.plan_json!.restrictions!.join(", ")}
                </div>
              )}
              {(selected.supplements_json?.items?.length ?? 0) > 0 && (
                <div>
                  <span className="text-gray-500">{t("plan.supplements_label")}:</span>{" "}
                  {selected.supplements_json!.items!.join(", ")}
                </div>
              )}
              {selected.plan_json?.description && (
                <div className="whitespace-pre-wrap text-gray-700">{selected.plan_json.description}</div>
              )}
            </div>
          )}
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded-md bg-brand px-3 py-1 text-xs text-white"
      >
        {open ? t("plan.hide") : t("plan.new")}
      </button>

      {open && (
        <form onSubmit={create} className="space-y-2 border-t pt-3">
          <div className="flex flex-wrap gap-2">
            <input
              className={`${input} flex-1`}
              placeholder={t("plan.title")}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <input type="date" className={input} value={effFrom} onChange={(e) => setEffFrom(e.target.value)} />
            <input
              type="number"
              className={`${input} w-28`}
              placeholder={t("plan.calories")}
              value={calories}
              onChange={(e) => setCalories(e.target.value)}
            />
          </div>
          <input
            className={`${input} w-full`}
            placeholder={t("plan.restrictions")}
            value={restrictions}
            onChange={(e) => setRestrictions(e.target.value)}
          />
          <input
            className={`${input} w-full`}
            placeholder={t("plan.supplements")}
            value={supplements}
            onChange={(e) => setSupplements(e.target.value)}
          />
          <textarea
            className={`${input} h-20 w-full resize-none`}
            placeholder={t("plan.description")}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          {error && <div className="text-xs text-red-600">{error}</div>}
          <Button type="submit" disabled={busy}>
            {busy ? t("plan.saving") : t("plan.create")}
          </Button>
        </form>
      )}
    </div>
  );
}
