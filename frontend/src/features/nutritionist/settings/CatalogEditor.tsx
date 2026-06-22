import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../../lib/supabase";
import { Button } from "../../../components/ui/Button";
import type { TrackedIndicator } from "../../client/queries";

const CATALOG_KEY = "lab_indicators_top";

function blankIndicator(): TrackedIndicator {
  return { key: "", label_ru: "", label_en: "", unit: "", ref_min: null, ref_max: null };
}

/** Глобальный каталог показателей анализов (system_settings.lab_indicators_top). */
function useCatalog() {
  return useQuery({
    queryKey: [CATALOG_KEY],
    queryFn: async (): Promise<TrackedIndicator[]> => {
      const { data, error } = await supabase
        .from("system_settings")
        .select("value")
        .eq("key", CATALOG_KEY)
        .maybeSingle();
      if (error) throw error;
      const arr = (data?.value as TrackedIndicator[] | null) ?? [];
      return Array.isArray(arr) ? arr : [];
    },
  });
}

/** Редактор глобального каталога показателей анализов (источник «Добавить из каталога»). */
export function CatalogEditor() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const catalog = useCatalog();

  const [rows, setRows] = useState<TrackedIndicator[]>([]);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (catalog.data) {
      setRows(catalog.data.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)));
    }
  }, [catalog.data]);

  function update(i: number, patch: Partial<TrackedIndicator>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }
  function remove(i: number) {
    setRows((rs) => rs.filter((_, idx) => idx !== i));
  }
  function move(i: number, dir: -1 | 1) {
    setRows((rs) => {
      const j = i + dir;
      if (j < 0 || j >= rs.length) return rs;
      const copy = rs.slice();
      [copy[i], copy[j]] = [copy[j], copy[i]];
      return copy;
    });
  }

  async function save() {
    setOk("");
    setError("");
    const cleaned = rows
      .map((r, idx) => ({ ...r, key: r.key.trim(), order: idx + 1 }))
      .filter((r) => r.key);
    const keys = cleaned.map((r) => r.key);
    if (new Set(keys).size !== keys.length) {
      setError(t("settings.catalog.dup_key"));
      return;
    }
    setBusy(true);
    try {
      const { error: e } = await supabase
        .from("system_settings")
        .update({ value: cleaned })
        .eq("key", CATALOG_KEY);
      if (e) throw e;
      setRows(cleaned);
      setOk(t("settings.catalog.saved"));
      qc.invalidateQueries({ queryKey: [CATALOG_KEY] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("settings.catalog.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-2 py-1 text-sm";
  const num = (v: number | null) => (v == null ? "" : String(v));
  const parseNum = (s: string): number | null => {
    const v = s.trim();
    if (v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  if (catalog.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;
  if (catalog.error) return <div className="text-sm text-red-600">{t("settings.catalog.error")}</div>;

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">{t("settings.catalog.hint")}</p>
      <div className="space-y-2">
        {rows.length === 0 && (
          <div className="text-xs text-gray-400">{t("settings.catalog.empty")}</div>
        )}
        {rows.map((r, i) => (
          <div key={i} className="rounded-md border p-2">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
              <input
                className={input}
                placeholder={t("settings.catalog.key")}
                value={r.key}
                onChange={(e) => update(i, { key: e.target.value })}
              />
              <input
                className={input}
                placeholder={t("settings.catalog.label_ru")}
                value={r.label_ru}
                onChange={(e) => update(i, { label_ru: e.target.value })}
              />
              <input
                className={input}
                placeholder={t("settings.catalog.label_en")}
                value={r.label_en}
                onChange={(e) => update(i, { label_en: e.target.value })}
              />
              <input
                className={input}
                placeholder={t("settings.catalog.unit")}
                value={r.unit ?? ""}
                onChange={(e) => update(i, { unit: e.target.value })}
              />
              <input
                className={input}
                placeholder={t("settings.catalog.ref_min")}
                value={num(r.ref_min)}
                onChange={(e) => update(i, { ref_min: parseNum(e.target.value) })}
              />
              <input
                className={input}
                placeholder={t("settings.catalog.ref_max")}
                value={num(r.ref_max)}
                onChange={(e) => update(i, { ref_max: parseNum(e.target.value) })}
              />
            </div>
            <div className="mt-1 flex gap-2 text-xs">
              <button type="button" className="text-gray-500 hover:text-brand" onClick={() => move(i, -1)}>
                ↑
              </button>
              <button type="button" className="text-gray-500 hover:text-brand" onClick={() => move(i, 1)}>
                ↓
              </button>
              <button type="button" className="text-red-600 hover:underline" onClick={() => remove(i)}>
                {t("settings.catalog.remove")}
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" onClick={() => setRows((rs) => [...rs, blankIndicator()])}>
          {t("settings.catalog.add")}
        </Button>
        <Button type="button" onClick={save} disabled={busy}>
          {busy ? t("settings.catalog.saving") : t("settings.catalog.save")}
        </Button>
        {ok && <span className="text-xs text-green-600">{ok}</span>}
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    </div>
  );
}
