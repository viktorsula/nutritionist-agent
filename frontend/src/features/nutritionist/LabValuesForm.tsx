import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Button } from "../../components/ui/Button";
import type { TrackedIndicator, LabResult } from "../client/queries";

const today = () => new Date().toISOString().slice(0, 10);

/**
 * Форма ввода значений анализов клиента (кабинет нутрициолога).
 * Пишет в lab_results (source='nutritionist') под RLS. Показатель выбирается
 * из настроенных для клиента (tracked_lab_indicators).
 */
export function LabValuesForm({
  clientId,
  indicators,
}: {
  clientId: string;
  indicators: TrackedIndicator[];
}) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const lang = i18n.language.startsWith("en") ? "en" : "ru";

  const [indicator, setIndicator] = useState("");
  const [value, setValue] = useState("");
  const [measuredAt, setMeasuredAt] = useState(today());
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  const usable = indicators.filter((i) => i.key.trim());
  const labelOf = (i: TrackedIndicator) =>
    (lang === "en" ? i.label_en : i.label_ru) || i.key;
  const unitOf = useMemo(
    () => usable.find((i) => i.key === indicator)?.unit ?? null,
    [usable, indicator],
  );

  // Последние внесённые значения для клиента (для контроля ввода).
  const recent = useQuery({
    queryKey: ["lab_results_recent", clientId],
    queryFn: async (): Promise<LabResult[]> => {
      const { data, error: e } = await supabase
        .from("lab_results")
        .select("measured_at,indicator,value,unit")
        .eq("client_id", clientId)
        .order("measured_at", { ascending: false })
        .limit(8);
      if (e) throw e;
      return data ?? [];
    },
  });

  async function save() {
    setOk("");
    setError("");
    const num = Number(value.trim());
    if (!indicator) {
      setError(t("labs_values.no_indicator"));
      return;
    }
    if (value.trim() === "" || !Number.isFinite(num)) {
      setError(t("labs_values.bad_value"));
      return;
    }
    setBusy(true);
    try {
      const { error: e } = await supabase.from("lab_results").insert({
        client_id: clientId,
        indicator,
        value: num,
        unit: unitOf,
        measured_at: measuredAt,
        source: "nutritionist",
      });
      if (e) throw e;
      setOk(t("labs_values.saved"));
      setValue("");
      // Обновляем и список «последних» (этот компонент), и график клиента.
      qc.invalidateQueries({ queryKey: ["lab_results_recent", clientId] });
      qc.invalidateQueries({ queryKey: ["lab_results", clientId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("labs_values.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3 border-t pt-4">
      <h3 className="text-sm font-semibold text-gray-700">{t("labs_values.title")}</h3>
      {usable.length === 0 ? (
        <p className="text-xs text-gray-400">{t("labs_values.need_indicators")}</p>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <select
              className={input}
              value={indicator}
              onChange={(e) => setIndicator(e.target.value)}
            >
              <option value="">{t("labs_values.indicator")}</option>
              {usable.map((i) => (
                <option key={i.key} value={i.key}>
                  {labelOf(i)} ({i.key})
                </option>
              ))}
            </select>
            <input
              type="number"
              step="any"
              className={`${input} w-28`}
              placeholder={t("labs_values.value")}
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
            {unitOf && <span className="text-xs text-gray-500">{unitOf}</span>}
            <input
              type="date"
              className={input}
              value={measuredAt}
              onChange={(e) => setMeasuredAt(e.target.value)}
            />
            <Button type="button" onClick={save} disabled={busy}>
              {busy ? t("labs_values.saving") : t("labs_values.add")}
            </Button>
          </div>

          {ok && <div className="text-sm text-green-600">{ok}</div>}
          {error && <div className="text-sm text-red-600">{error}</div>}

          {(recent.data ?? []).length > 0 && (
            <div className="mt-2">
              <div className="mb-1 text-xs font-medium text-gray-600">
                {t("labs_values.recent")}
              </div>
              <ul className="space-y-0.5 text-xs text-gray-600">
                {(recent.data ?? []).map((r, idx) => (
                  <li key={idx}>
                    {r.measured_at} — {r.indicator}: {r.value}
                    {r.unit ? ` ${r.unit}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
