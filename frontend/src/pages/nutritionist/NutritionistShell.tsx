import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Header } from "../../components/Header";
import { LabIndicatorsManager } from "../../features/nutritionist/LabIndicatorsManager";
import { AlertsPanel } from "../../features/nutritionist/AlertsPanel";
import { Registry } from "../../features/nutritionist/Registry";
import { ClientCard } from "../../features/nutritionist/ClientCard";
import { NutritionistChat } from "../../features/nutritionist/NutritionistChat";
import type { RegistryRow } from "../../features/nutritionist/queries";

type Tab = "alerts" | "registry" | "labs" | "assistant" | "analytics" | "settings";

/**
 * Каркас кабинета нутрициолога — табы (реестр / аналитика / настройки)
 * + центральная панель. Наполнение — Фаза 3.
 */
export function NutritionistShell() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("alerts");
  const [selectedClient, setSelectedClient] = useState<RegistryRow | null>(null);

  const tabs: Tab[] = ["alerts", "registry", "labs", "assistant", "analytics", "settings"];

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <Header />
      <div className="flex flex-1 gap-4 p-4">
        <nav className="w-56 shrink-0 rounded-xl bg-white p-3 shadow-sm">
          {tabs.map((item) => (
            <button
              key={item}
              onClick={() => setTab(item)}
              className={`mb-1 block w-full rounded-md px-3 py-2 text-left text-sm ${
                tab === item ? "bg-brand text-white" : "text-gray-600 hover:bg-brand-light"
              }`}
            >
              {t(`nutritionist.${item}`)}
            </button>
          ))}
        </nav>

        <main className="flex-1 rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-4 text-sm font-semibold text-brand-dark">
            {t(`nutritionist.${tab}`)}
          </h2>
          {tab === "alerts" ? (
            <AlertsPanel />
          ) : tab === "registry" ? (
            selectedClient ? (
              <ClientCard client={selectedClient} onBack={() => setSelectedClient(null)} />
            ) : (
              <Registry onOpen={setSelectedClient} />
            )
          ) : tab === "labs" ? (
            <LabIndicatorsManager />
          ) : tab === "assistant" ? (
            <NutritionistChat />
          ) : (
            <p className="text-xs text-gray-400">{t("nutritionist.placeholder")}</p>
          )}
        </main>
      </div>
    </div>
  );
}
