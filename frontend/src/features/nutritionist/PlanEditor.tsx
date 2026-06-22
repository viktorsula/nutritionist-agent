import { useState, type FormEvent } from "react";
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

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [effFrom, setEffFrom] = useState(today());
  const [calories, setCalories] = useState("");
  const [restrictions, setRestrictions] = useState("");
  const [supplements, setSupplements] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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
      {(plans.data ?? []).length > 0 && (
        <ul className="space-y-1">
          {(plans.data ?? []).map((pl) => (
            <li key={pl.id} className="flex justify-between gap-2 text-xs">
              <span className={pl.is_active ? "font-medium text-gray-800" : "text-gray-400"}>
                v{pl.version}. {pl.title}
                {pl.is_active ? ` · ${t("plan.active")}` : ""}
              </span>
              <span className="text-gray-400">
                {pl.effective_from}
                {pl.effective_to ? ` – ${pl.effective_to}` : ""}
              </span>
            </li>
          ))}
        </ul>
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
