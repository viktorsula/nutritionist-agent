import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/Button";

const CLIENT_STATUSES = ["lead", "onboarding", "active", "paused", "completed", "archived"];
const PAYMENT_STATUSES = ["trial", "active", "inactive"];

/**
 * Редактор статусов клиента (2 оси): client_status (жизненный цикл; «completed» = «Поддержка»)
 * + payment_status/paid_until (оплата). Пишет через бэкенд-эндпоинт с аудитом; авто-блок доступа
 * по истёкшему paid_until — на стороне access_rules.
 */
export function StatusEditor({
  clientId,
  clientStatus,
  paymentStatus,
  paidUntil,
}: {
  clientId: string;
  clientStatus?: string | null;
  paymentStatus?: string | null;
  paidUntil?: string | null;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();

  const [cs, setCs] = useState(clientStatus ?? "lead");
  const [ps, setPs] = useState(paymentStatus ?? "trial");
  const [pu, setPu] = useState((paidUntil ?? "").slice(0, 10));
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setCs(clientStatus ?? "lead");
    setPs(paymentStatus ?? "trial");
    setPu((paidUntil ?? "").slice(0, 10));
    setOk(false);
    setErr("");
  }, [clientId, clientStatus, paymentStatus, paidUntil]);

  async function save() {
    setBusy(true);
    setOk(false);
    setErr("");
    try {
      await api.updateClientStatus(clientId, {
        client_status: cs,
        payment_status: ps,
        paid_until: pu,
      });
      setOk(true);
      qc.invalidateQueries({ queryKey: ["client_row", clientId] });
      qc.invalidateQueries({ queryKey: ["registry_clients"] });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const selectCls = "w-full rounded-md border px-2 py-1 text-sm";
  return (
    <div className="space-y-2">
      <div>
        <div className="mb-1 text-xs text-gray-500">{t("card.status_lifecycle")}</div>
        <select className={selectCls} value={cs} onChange={(e) => { setCs(e.target.value); setOk(false); }}>
          {CLIENT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`registry.status_value.${s}`, { defaultValue: s })}
            </option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <div className="mb-1 text-xs text-gray-500">{t("card.status_payment")}</div>
          <select className={selectCls} value={ps} onChange={(e) => { setPs(e.target.value); setOk(false); }}>
            {PAYMENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`registry.payment_value.${s}`, { defaultValue: s })}
              </option>
            ))}
          </select>
        </div>
        <div>
          <div className="mb-1 text-xs text-gray-500">{t("card.status_paid_until")}</div>
          <input
            type="date"
            className={selectCls}
            value={pu}
            onChange={(e) => { setPu(e.target.value); setOk(false); }}
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Button type="button" onClick={save} disabled={busy}>
          {busy ? t("card.saving") : t("card.status_save")}
        </Button>
        {ok && <span className="text-xs text-green-600">{t("card.saved")}</span>}
      </div>
      {err && <div className="text-xs text-red-600">{err}</div>}
    </div>
  );
}
