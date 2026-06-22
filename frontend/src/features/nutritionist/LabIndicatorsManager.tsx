import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Button } from "../../components/ui/Button";
import type { TrackedIndicator } from "../client/queries";
import { LabValuesForm } from "./LabValuesForm";

interface ClientRow {
  id: string;
  name: string | null;
}

/** Пустой показатель для новой строки. */
function blankIndicator(): TrackedIndicator {
  return { key: "", label_ru: "", label_en: "", unit: "", ref_min: null, ref_max: null };
}

/** Список клиентов (под RLS нутрициолог видит всех). */
function useClients() {
  return useQuery({
    queryKey: ["nutri_clients"],
    queryFn: async (): Promise<ClientRow[]> => {
      const { data, error } = await supabase
        .from("clients")
        .select("id,name")
        .order("name", { ascending: true });
      if (error) throw error;
      return data ?? [];
    },
  });
}

/** Каталог показателей по умолчанию (system_settings.lab_indicators_top). */
function useCatalog() {
  return useQuery({
    queryKey: ["lab_indicators_top"],
    queryFn: async (): Promise<TrackedIndicator[]> => {
      const { data, error } = await supabase
        .from("system_settings")
        .select("value")
        .eq("key", "lab_indicators_top")
        .maybeSingle();
      if (error) throw error;
      const arr = (data?.value as TrackedIndicator[] | null) ?? [];
      return Array.isArray(arr) ? arr : [];
    },
  });
}

/**
 * Кабинет нутрициолога: выбор показателей анализов для графика динамики
 * у конкретного клиента. Пишет в client_profiles.tracked_lab_indicators (под RLS).
 */
export function LabIndicatorsManager() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const clients = useClients();
  const catalog = useCatalog();

  const [clientId, setClientId] = useState("");
  const [rows, setRows] = useState<TrackedIndicator[]>([]);
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [error, setError] = useState("");

  // Загрузка выбранных показателей при смене клиента.
  useEffect(() => {
    setOk("");
    setError("");
    if (!clientId) {
      setRows([]);
      return;
    }
    (async () => {
      const { data, error: e } = await supabase
        .from("client_profiles")
        .select("tracked_lab_indicators")
        .eq("client_id", clientId)
        .maybeSingle();
      if (e) {
        setError(e.message);
        return;
      }
      const arr = (data?.tracked_lab_indicators as TrackedIndicator[] | null) ?? [];
      setRows(
        (Array.isArray(arr) ? arr : [])
          .slice()
          .sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
      );
    })();
  }, [clientId]);

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
  function addFromCatalog(key: string) {
    if (!key) return;
    const c = (catalog.data ?? []).find((x) => x.key === key);
    if (!c) return;
    if (rows.some((r) => r.key === c.key)) return;
    setRows((rs) => [...rs, { ...blankIndicator(), ...c }]);
  }

  async function save() {
    setOk("");
    setError("");
    // Валидация: ключ обязателен и уникален.
    const cleaned = rows
      .map((r, idx) => ({ ...r, key: r.key.trim(), order: idx + 1 }))
      .filter((r) => r.key);
    const keys = cleaned.map((r) => r.key);
    if (new Set(keys).size !== keys.length) {
      setError(t("labs_admin.dup_key"));
      return;
    }
    setBusy(true);
    try {
      const { error: e } = await supabase
        .from("client_profiles")
        .upsert(
          { client_id: clientId, tracked_lab_indicators: cleaned },
          { onConflict: "client_id" },
        );
      if (e) throw e;
      setRows(cleaned);
      setOk(t("labs_admin.saved"));
      qc.invalidateQueries({ queryKey: ["client_profile", clientId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("labs_admin.error"));
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-md border px-2 py-1 text-sm";
  const num = (v: number | null) => (v == null ? "" : String(v));
  const parseNum = (s: string): number | null => {
    const t2 = s.trim();
    if (t2 === "") return null;
    const n = Number(t2);
    return Number.isFinite(n) ? n : null;
  };

  return (
    <div className="max-w-3xl space-y-4">
      <h3 className="text-sm font-semibold text-gray-700">{t("labs_admin.title")}</h3>
      <p className="text-xs text-gray-500">{t("labs_admin.hint")}</p>

      <select
        className="w-full max-w-sm rounded-md border px-3 py-2 text-sm"
        value={clientId}
        onChange={(e) => setClientId(e.target.value)}
      >
        <option value="">{t("labs_admin.select_client")}</option>
        {(clients.data ?? []).map((c) => (
          <option key={c.id} value={c.id}>
            {c.name || c.id}
          </option>
        ))}
      </select>

      {clientId && (
        <>
          <div className="space-y-2">
            {rows.length === 0 && (
              <div className="text-xs text-gray-400">{t("labs_admin.empty")}</div>
            )}
            {rows.map((r, i) => (
              <div key={i} className="rounded-md border p-2">
                <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
                  <input
                    className={input}
                    placeholder={t("labs_admin.key")}
                    value={r.key}
                    onChange={(e) => update(i, { key: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder={t("labs_admin.label_ru")}
                    value={r.label_ru}
                    onChange={(e) => update(i, { label_ru: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder={t("labs_admin.label_en")}
                    value={r.label_en}
                    onChange={(e) => update(i, { label_en: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder={t("labs_admin.unit")}
                    value={r.unit ?? ""}
                    onChange={(e) => update(i, { unit: e.target.value })}
                  />
                  <input
                    className={input}
                    placeholder={t("labs_admin.ref_min")}
                    value={num(r.ref_min)}
                    onChange={(e) => update(i, { ref_min: parseNum(e.target.value) })}
                  />
                  <input
                    className={input}
                    placeholder={t("labs_admin.ref_max")}
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
                    {t("labs_admin.remove")}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <select
              className="rounded-md border px-2 py-1 text-sm"
              value=""
              onChange={(e) => addFromCatalog(e.target.value)}
            >
              <option value="">{t("labs_admin.add_from_catalog")}</option>
              {(catalog.data ?? []).map((c) => (
                <option key={c.key} value={c.key}>
                  {c.label_ru} ({c.key})
                </option>
              ))}
            </select>
            <Button
              type="button"
              onClick={() => setRows((rs) => [...rs, blankIndicator()])}
            >
              {t("labs_admin.add_custom")}
            </Button>
            <Button type="button" onClick={save} disabled={busy}>
              {busy ? t("labs_admin.saving") : t("labs_admin.save")}
            </Button>
          </div>

          {ok && <div className="text-sm text-green-600">{ok}</div>}
          {error && <div className="text-sm text-red-600">{error}</div>}

          <LabValuesForm clientId={clientId} indicators={rows} />
        </>
      )}
    </div>
  );
}
