import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api, type ControlledMetric } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import { useControlledMetrics } from "./queries";

// Встроенные показатели с детерминированным распознаванием в диалоге (ключи известны агенту).
const PRESETS: { key: string; unit: string }[] = [
  { key: "weight", unit: "кг" },
  { key: "waist", unit: "см" },
  { key: "neck", unit: "см" },
  { key: "hips", unit: "см" },
  { key: "sleep", unit: "ч" },
];

/**
 * Каталог контролируемых показателей клиента (динамические поля). Нутрициолог выбирает,
 * какие показатели контролировать: встроенные (вес/талия/шея/бёдра/сон) + произвольные
 * (пульс, стресс…). Каталог питает пикер «ожидаемого ответа» в напоминаниях.
 */
export function MetricsCatalogEditor({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const metrics = useControlledMetrics(clientId);

  const [items, setItems] = useState<ControlledMetric[]>([]);
  const [label, setLabel] = useState("");
  const [unit, setUnit] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => setItems(metrics.data ?? []), [metrics.data]);

  const has = (key: string) => items.some((m) => m.key === key);
  const dirty = () => setOk(false);

  function addPreset(key: string, presetUnit: string) {
    if (has(key)) return;
    setItems([...items, { key, label_ru: t(`metrics.preset.${key}`), unit: presetUnit }]);
    dirty();
  }

  function addCustom() {
    const name = label.trim();
    if (!name) return;
    const key = name.toLowerCase().replace(/\s+/g, "_");
    if (has(key)) return;
    setItems([...items, { key, label_ru: name, unit: unit.trim(), category: "custom" }]);
    setLabel("");
    setUnit("");
    dirty();
  }

  function remove(key: string) {
    setItems(items.filter((m) => m.key !== key));
    dirty();
  }

  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api.setControlledMetrics(clientId, items);
      qc.invalidateQueries({ queryKey: ["controlled_metrics", clientId] });
      setOk(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      <div className="text-xs text-gray-400">{t("metrics.hint")}</div>

      {items.length === 0 ? (
        <div className="text-xs text-gray-400">{t("metrics.empty")}</div>
      ) : (
        <ul className="space-y-1">
          {items.map((m) => (
            <li key={m.key} className="flex items-center justify-between gap-2 text-xs">
              <span className="text-gray-800">
                {m.label_ru}
                {m.unit ? <span className="text-gray-400"> · {m.unit}</span> : null}
              </span>
              <button className="text-red-600 hover:underline" onClick={() => remove(m.key)}>
                {t("metrics.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap gap-1">
        {PRESETS.map((p) => (
          <button
            key={p.key}
            disabled={has(p.key)}
            onClick={() => addPreset(p.key, p.unit)}
            className="rounded-full border px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-40"
          >
            + {t(`metrics.preset.${p.key}`)}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t pt-2">
        <input
          className={`${input} flex-1`}
          placeholder={t("metrics.custom_label")}
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
        <input
          className={`${input} w-20`}
          placeholder={t("metrics.custom_unit")}
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
        />
        <button className="text-xs text-blue-600 hover:underline" onClick={addCustom}>
          {t("metrics.add_custom")}
        </button>
      </div>

      {error && <div className="text-xs text-red-600">{error}</div>}
      <div className="flex items-center gap-2">
        <Button type="button" onClick={save} disabled={busy}>
          {busy ? t("metrics.saving") : t("metrics.save")}
        </Button>
        {ok && <span className="text-xs text-green-600">{t("metrics.saved")}</span>}
      </div>
    </div>
  );
}
