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
    // На десктопе (lg) высота фиксируется по экрану, внутренний скролл по колонкам —
    // чат не растягивается вместе со страницей и всегда виден целиком.
    // На мобильных — обычный поток страницы.
    <div className="flex min-h-screen flex-col bg-gray-50 lg:h-screen lg:min-h-0 lg:overflow-hidden">
      <Header />
      <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:min-h-0 lg:grid-cols-[300px_1fr_468px]">
        <aside className="flex flex-col lg:min-h-0">
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("client.dashboard")}
          </h2>
          <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
            <DashboardPanel clientId={clientId} />
          </div>
        </aside>

        <main className="flex flex-col lg:min-h-0">
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("client.main")}
          </h2>
          <div className="flex-1 pr-1 lg:min-h-0 lg:overflow-y-auto">
            <MainPanel clientId={clientId} />
          </div>
        </main>

        <section className="flex flex-col rounded-xl border bg-white p-4 shadow-sm lg:min-h-0">
          <h2 className="mb-2 text-sm font-semibold text-brand-dark">{t("client.chat")}</h2>
          <div className="min-h-0 flex-1">
            <ChatPanel clientId={clientId} />
          </div>
        </section>
      </div>
    </div>
  );
}
