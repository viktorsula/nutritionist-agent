import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { CreateClientForm } from "../clients/CreateClientForm";
import { useClientsList } from "./queries";
import { daysUntil, expiryKind } from "./expiry";

// Значения статусов из схемы — стабильные опции фильтра (даже если в данных пусто).
const STATUS_OPTIONS = ["lead", "onboarding", "active", "paused", "completed", "archived"];
const PAYMENT_OPTIONS = ["trial", "active", "inactive"];

/** Реестр клиентов: список + фильтры по столбцам + создание; клик по строке открывает карточку. */
export function Registry({ onOpen }: { onOpen: (clientId: string) => void }) {
  const { t } = useTranslation();
  const clients = useClientsList();
  const [showCreate, setShowCreate] = useState(false);

  // Фильтры по столбцам
  const [fName, setFName] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fPayment, setFPayment] = useState("");
  const [fGoal, setFGoal] = useState("");

  const hasFilters = !!(fName || fStatus || fPayment || fGoal);

  const rows = useMemo(() => {
    const all = clients.data ?? [];
    const name = fName.trim().toLowerCase();
    const goal = fGoal.trim().toLowerCase();
    return all.filter((c) => {
      if (name && !(c.name ?? "").toLowerCase().includes(name)) return false;
      if (fStatus && c.client_status !== fStatus) return false;
      if (fPayment && c.payment_status !== fPayment) return false;
      if (goal && !(c.client_profiles?.goals ?? "").toLowerCase().includes(goal)) return false;
      return true;
    });
  }, [clients.data, fName, fStatus, fPayment, fGoal]);

  function resetFilters() {
    setFName("");
    setFStatus("");
    setFPayment("");
    setFGoal("");
  }

  // Человекочитаемые подписи статусов/оплаты (fallback на сырое значение).
  const statusLabel = (s: string | null) =>
    s ? t(`registry.status_value.${s}`, { defaultValue: s }) : "—";
  const paymentLabel = (s: string | null) =>
    s ? t(`registry.payment_value.${s}`, { defaultValue: s }) : "—";

  const filterInput = "w-full rounded border px-2 py-1 text-xs";
  const total = (clients.data ?? []).length;

  // Индикатор срока тарифа: цвет + подпись «ещё N дн.» / «истёк».
  function expiryBadge(paidUntil: string | null) {
    const kind = expiryKind(paidUntil);
    if (kind === "none") return <span className="text-gray-400">—</span>;
    const d = daysUntil(paidUntil)!;
    const cls =
      kind === "expired"
        ? "text-red-600 font-medium"
        : kind === "soon"
          ? "text-amber-600 font-medium"
          : "text-gray-600";
    const note =
      kind === "expired"
        ? t("registry.expiry_expired")
        : d === 0
          ? t("registry.expiry_today")
          : t("registry.expiry_left", { n: d });
    return (
      <span className={cls} title={paidUntil ?? ""}>
        {paidUntil} <span className="text-[11px]">({note})</span>
      </span>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {hasFilters
            ? t("registry.count_filtered", { n: rows.length, total })
            : t("registry.count", { n: total })}
        </span>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="rounded-md bg-brand px-3 py-1 text-xs text-white"
        >
          {showCreate ? t("registry.hide_create") : t("registry.add")}
        </button>
      </div>

      {showCreate && (
        <div className="rounded-md border p-3">
          <CreateClientForm />
        </div>
      )}

      {clients.isLoading ? (
        <div className="text-xs text-gray-400">{t("loading")}</div>
      ) : clients.error ? (
        <div className="text-sm text-red-600">{t("registry.error")}</div>
      ) : total === 0 ? (
        <div className="py-8 text-center text-xs text-gray-400">{t("registry.empty")}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-gray-500">
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium">{t("registry.name")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.status")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.payment")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.paid_until")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.goal")}</th>
                <th className="py-2 font-medium">{t("registry.weight")}</th>
              </tr>
              {/* Строка фильтров по столбцам */}
              <tr className="border-b align-top">
                <th className="py-1 pr-3 font-normal">
                  <input
                    className={filterInput}
                    placeholder={t("registry.filter_name")}
                    value={fName}
                    onChange={(e) => setFName(e.target.value)}
                  />
                </th>
                <th className="py-1 pr-3 font-normal">
                  <select className={filterInput} value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
                    <option value="">{t("registry.filter_all")}</option>
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {statusLabel(s)}
                      </option>
                    ))}
                  </select>
                </th>
                <th className="py-1 pr-3 font-normal">
                  <select className={filterInput} value={fPayment} onChange={(e) => setFPayment(e.target.value)}>
                    <option value="">{t("registry.filter_all")}</option>
                    {PAYMENT_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {paymentLabel(s)}
                      </option>
                    ))}
                  </select>
                </th>
                <th className="py-1 pr-3 font-normal">
                  {hasFilters && (
                    <button
                      onClick={resetFilters}
                      className="rounded border px-2 py-1 text-xs text-gray-500 hover:bg-brand-light"
                    >
                      {t("registry.filter_reset")}
                    </button>
                  )}
                </th>
                <th className="py-1 pr-3 font-normal">
                  <input
                    className={filterInput}
                    placeholder={t("registry.filter_goal")}
                    value={fGoal}
                    onChange={(e) => setFGoal(e.target.value)}
                  />
                </th>
                <th className="py-1 font-normal" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-xs text-gray-400">
                    {t("registry.no_match")}
                  </td>
                </tr>
              ) : (
                rows.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => onOpen(c.id)}
                    className="cursor-pointer border-b hover:bg-brand-light"
                  >
                    <td className="py-2 pr-3 font-medium text-gray-800">{c.name || "—"}</td>
                    <td className="py-2 pr-3 text-gray-600">{statusLabel(c.client_status)}</td>
                    <td className="py-2 pr-3 text-gray-600">{paymentLabel(c.payment_status)}</td>
                    <td className="py-2 pr-3">{expiryBadge(c.paid_until)}</td>
                    <td className="py-2 pr-3 text-gray-600">{c.client_profiles?.goals || "—"}</td>
                    <td className="py-2 text-gray-600">
                      {c.client_profiles?.weight != null
                        ? `${c.client_profiles.weight}${
                            c.client_profiles.target_weight != null
                              ? ` → ${c.client_profiles.target_weight}`
                              : ""
                          }`
                        : "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
