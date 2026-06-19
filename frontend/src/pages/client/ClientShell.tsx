import { useTranslation } from "react-i18next";
import { Header } from "../../components/Header";
import { useAuth } from "../../auth/AuthProvider";
import { DashboardPanel } from "../../features/client/DashboardPanel";
import { MainPanel } from "../../features/client/MainPanel";
import { ChatPanel } from "../../features/client/ChatPanel";

/**
 * Кабинет клиента — 3 колонки:
 * слева — панель управления (профиль/статус/цель/рекомендации),
 * по центру — рабочая панель (напоминания + графики веса/КБЖУ/анализов),
 * справа — чат с агентом.
 */
export function ClientShell() {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  const clientId = appUser?.client_id ?? "";

  return (
    <div className="flex min-h-screen flex-col bg-gray-50">
      <Header />
      <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[300px_1fr_360px]">
        <aside>
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("client.dashboard")}
          </h2>
          <DashboardPanel clientId={clientId} />
        </aside>

        <main>
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("client.main")}
          </h2>
          <MainPanel clientId={clientId} />
        </main>

        <section className="flex flex-col rounded-xl border bg-white p-4 shadow-sm">
          <h2 className="mb-2 text-sm font-semibold text-brand-dark">{t("client.chat")}</h2>
          <div className="min-h-0 flex-1">
            <ChatPanel clientId={clientId} />
          </div>
        </section>
      </div>
    </div>
  );
}
