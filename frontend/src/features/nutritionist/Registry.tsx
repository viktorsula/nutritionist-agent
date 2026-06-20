import { useState } from "react";
import { useTranslation } from "react-i18next";
import { CreateClientForm } from "../clients/CreateClientForm";
import { useClientsList, type RegistryRow } from "./queries";

/** Реестр клиентов: список + создание; клик по строке открывает карточку. */
export function Registry({ onOpen }: { onOpen: (client: RegistryRow) => void }) {
  const { t } = useTranslation();
  const clients = useClientsList();
  const [showCreate, setShowCreate] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {t("registry.count", { n: (clients.data ?? []).length })}
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
      ) : (clients.data ?? []).length === 0 ? (
        <div className="py-8 text-center text-xs text-gray-400">{t("registry.empty")}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-gray-500">
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium">{t("registry.name")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.status")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.payment")}</th>
                <th className="py-2 pr-3 font-medium">{t("registry.goal")}</th>
                <th className="py-2 font-medium">{t("registry.weight")}</th>
              </tr>
            </thead>
            <tbody>
              {(clients.data ?? []).map((c) => (
                <tr
                  key={c.id}
                  onClick={() => onOpen(c)}
                  className="cursor-pointer border-b hover:bg-brand-light"
                >
                  <td className="py-2 pr-3 font-medium text-gray-800">{c.name || "—"}</td>
                  <td className="py-2 pr-3 text-gray-600">{c.client_status}</td>
                  <td className="py-2 pr-3 text-gray-600">{c.payment_status}</td>
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
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
