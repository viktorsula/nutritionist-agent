import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Header } from "../../components/Header";
import { CreateClientForm } from "../../features/clients/CreateClientForm";

type Tab = "registry" | "analytics" | "settings";

/**
 * Каркас кабинета нутрициолога — табы (реестр / аналитика / настройки)
 * + центральная панель. Наполнение — Фаза 3.
 */
export function NutritionistShell() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>("registry");

  const tabs: Tab[] = ["registry", "analytics", "settings"];

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
          {tab === "registry" ? (
            <CreateClientForm />
          ) : (
            <p className="text-xs text-gray-400">{t("nutritionist.placeholder")}</p>
          )}
        </main>
      </div>
    </div>
  );
}
