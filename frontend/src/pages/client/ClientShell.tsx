import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Header } from "../../components/Header";
import { useAuth } from "../../auth/AuthProvider";
import { DashboardPanel } from "../../features/client/DashboardPanel";
import { MainPanel } from "../../features/client/MainPanel";
import { ChatPanel } from "../../features/client/ChatPanel";

// Границы ширины чата (px) и ключи localStorage для сохранения раскладки.
const CHAT_MIN = 320;
const CHAT_MAX = 760;
const LS_WIDTH = "client.chatWidth";
const LS_VISIBLE = "client.chatVisible";

/**
 * Кабинет клиента — 3 колонки:
 * слева — панель управления (профиль/статус/цель/рекомендации),
 * по центру — рабочая панель (напоминания + графики веса/КБЖУ/анализов),
 * справа — чат с агентом.
 *
 * Чат можно скрыть/показать и менять его ширину перетаскиванием границы;
 * настройки раскладки сохраняются в localStorage (как в кабинете нутрициолога).
 */
export function ClientShell() {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  const clientId = appUser?.client_id ?? "";

  const [chatVisible, setChatVisible] = useState<boolean>(
    () => localStorage.getItem(LS_VISIBLE) !== "0",
  );
  const [chatWidth, setChatWidth] = useState<number>(() => {
    const v = Number(localStorage.getItem(LS_WIDTH));
    return v >= CHAT_MIN && v <= CHAT_MAX ? v : 468;
  });

  // Фиксированные ширины актуальны только на десктопе (lg); на мобильных колонки
  // складываются в поток.
  const [isDesktop, setIsDesktop] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  function toggleChat() {
    setChatVisible((v) => {
      localStorage.setItem(LS_VISIBLE, v ? "0" : "1");
      return !v;
    });
  }

  // Перетаскивание границы: ширина чата = расстояние от правого края окна
  // до курсора (минус правый отступ p-4 = 16px), с зажимом в [MIN, MAX].
  function startResize(e: React.PointerEvent) {
    e.preventDefault();
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    const onMove = (ev: PointerEvent) => {
      const w = window.innerWidth - ev.clientX - 16;
      setChatWidth(Math.min(CHAT_MAX, Math.max(CHAT_MIN, w)));
    };
    const onUp = () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      setChatWidth((w) => {
        localStorage.setItem(LS_WIDTH, String(w));
        return w;
      });
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  }

  return (
    // На десктопе (lg) высота фиксируется по экрану, внутренний скролл по колонкам —
    // чат не растягивается вместе со страницей и всегда виден целиком.
    // На мобильных — обычный поток страницы.
    <div className="flex min-h-screen flex-col bg-gray-50 lg:h-screen lg:min-h-0 lg:overflow-hidden">
      <Header />
      <div className="flex flex-1 flex-col gap-4 p-4 lg:min-h-0 lg:flex-row">
        {/* Левая колонка — панель управления */}
        <aside className="flex w-full shrink-0 flex-col lg:w-[300px] lg:min-h-0">
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("client.dashboard")}
          </h2>
          <div className="flex-1 lg:min-h-0 lg:overflow-y-auto">
            <DashboardPanel clientId={clientId} />
          </div>
        </aside>

        {/* Центральная колонка — рабочая панель */}
        <main className="flex min-w-0 flex-1 flex-col lg:min-h-0">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold text-brand-dark">{t("client.main")}</h2>
            {!chatVisible && (
              <button
                onClick={toggleChat}
                className="rounded-md border px-2 py-1 text-xs text-gray-600 hover:bg-brand-light"
              >
                ‹ {t("client.show_chat")}
              </button>
            )}
          </div>
          <div className="flex-1 pr-1 lg:min-h-0 lg:overflow-y-auto">
            <MainPanel clientId={clientId} />
          </div>
        </main>

        {/* Перетаскиваемая граница — только на десктопе при видимом чате */}
        {chatVisible && isDesktop && (
          <div
            onPointerDown={startResize}
            title={t("client.resize_hint")}
            className="hidden w-1.5 shrink-0 cursor-col-resize rounded bg-gray-200 hover:bg-brand lg:block"
          />
        )}

        {/* Правая колонка — чат с агентом */}
        {chatVisible && (
          <section
            style={isDesktop ? { width: chatWidth } : undefined}
            className="flex w-full shrink-0 flex-col rounded-xl border bg-white p-4 shadow-sm lg:min-h-0"
          >
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-brand-dark">{t("client.chat")}</h2>
              <button
                onClick={toggleChat}
                className="rounded-md border px-2 py-1 text-xs text-gray-600 hover:bg-brand-light"
              >
                {t("client.hide_chat")} ›
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <ChatPanel clientId={clientId} />
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
