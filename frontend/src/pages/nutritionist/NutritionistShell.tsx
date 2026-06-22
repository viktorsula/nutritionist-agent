import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Header } from "../../components/Header";
import { LabIndicatorsManager } from "../../features/nutritionist/LabIndicatorsManager";
import { AlertsPanel } from "../../features/nutritionist/AlertsPanel";
import { Registry } from "../../features/nutritionist/Registry";
import { ClientCard } from "../../features/nutritionist/ClientCard";
import { NutritionistChat } from "../../features/nutritionist/NutritionistChat";
import { SettingsPanel } from "../../features/nutritionist/SettingsPanel";
import { AnalyticsPanel } from "../../features/nutritionist/AnalyticsPanel";
import type { CenterView, AgentAnalysis } from "../../features/nutritionist/view";

type Tool = "alerts" | "registry" | "labs" | "analytics" | "settings";

const TOOLS: Tool[] = ["alerts", "registry", "labs", "analytics", "settings"];

// Границы ширины чата (px) и ключи localStorage для сохранения раскладки.
const CHAT_MIN = 320;
const CHAT_MAX = 760;
const LS_WIDTH = "nutri.chatWidth";
const LS_VISIBLE = "nutri.chatVisible";

/**
 * Каркас кабинета нутрициолога — 3 колонки:
 * слева — панель управления (инструменты), по центру — рабочая панель
 * (вывод выбранного инструмента), справа — постоянный чат с агентом.
 *
 * Чат можно скрыть/показать и менять его ширину перетаскиванием границы;
 * настройки раскладки сохраняются в localStorage.
 */
export function NutritionistShell() {
  const { t } = useTranslation();
  const [tool, setTool] = useState<Tool>("alerts");
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AgentAnalysis | null>(null);

  const [chatVisible, setChatVisible] = useState<boolean>(
    () => localStorage.getItem(LS_VISIBLE) !== "0",
  );
  const [chatWidth, setChatWidth] = useState<number>(() => {
    const v = Number(localStorage.getItem(LS_WIDTH));
    return v >= CHAT_MIN && v <= CHAT_MAX ? v : 468;
  });

  // Раскладка с фиксированными ширинами актуальна только на десктопе (lg);
  // на мобильных колонки складываются в поток.
  const [isDesktop, setIsDesktop] = useState<boolean>(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const handler = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  function selectTool(next: Tool) {
    setTool(next);
    setSelectedClientId(null); // каждый переход в инструмент — с чистого листа
  }

  // Директива вида от агента (Блок 2): переключаем центр под запрос из чата.
  function handleView(view: CenterView) {
    if (view.type === "client_card") {
      setSelectedClientId(view.client_id);
      setTool("registry");
    } else if (view.type === "analytics") {
      setSelectedClientId(null);
      setTool("analytics");
    } else if (view.type === "registry") {
      setSelectedClientId(null);
      setTool("registry");
    }
  }

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
    <div className="flex min-h-screen flex-col bg-gray-50 lg:h-screen lg:min-h-0 lg:overflow-hidden">
      <Header />
      <div className="flex flex-1 flex-col gap-4 p-4 lg:min-h-0 lg:flex-row">
        {/* Левая колонка — панель управления (инструменты) */}
        <aside className="w-full shrink-0 lg:w-56 lg:min-h-0">
          <h2 className="mb-2 px-1 text-sm font-semibold text-brand-dark">
            {t("nutritionist.dashboard")}
          </h2>
          <nav className="rounded-xl bg-white p-3 shadow-sm">
            {TOOLS.map((item) => (
              <button
                key={item}
                onClick={() => selectTool(item)}
                className={`mb-1 block w-full rounded-md px-3 py-2 text-left text-sm ${
                  tool === item ? "bg-brand text-white" : "text-gray-600 hover:bg-brand-light"
                }`}
              >
                {t(`nutritionist.${item}`)}
              </button>
            ))}
          </nav>
        </aside>

        {/* Центральная колонка — рабочая панель */}
        <main className="flex min-w-0 flex-1 flex-col lg:min-h-0">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold text-brand-dark">
              {t(`nutritionist.${tool}`)}
            </h2>
            {!chatVisible && (
              <button
                onClick={toggleChat}
                className="rounded-md border px-2 py-1 text-xs text-gray-600 hover:bg-brand-light"
              >
                ‹ {t("nutritionist.show_chat")}
              </button>
            )}
          </div>
          <div className="flex-1 rounded-xl bg-white p-4 shadow-sm lg:min-h-0 lg:overflow-y-auto">
            {tool === "alerts" ? (
              <AlertsPanel />
            ) : tool === "registry" ? (
              selectedClientId ? (
                <ClientCard clientId={selectedClientId} onBack={() => setSelectedClientId(null)} />
              ) : (
                <Registry onOpen={setSelectedClientId} />
              )
            ) : tool === "labs" ? (
              <LabIndicatorsManager />
            ) : tool === "analytics" ? (
              <AnalyticsPanel analysis={analysis} />
            ) : tool === "settings" ? (
              <SettingsPanel />
            ) : (
              <p className="text-xs text-gray-400">{t("nutritionist.placeholder")}</p>
            )}
          </div>
        </main>

        {/* Перетаскиваемая граница — только на десктопе при видимом чате */}
        {chatVisible && isDesktop && (
          <div
            onPointerDown={startResize}
            title="Потяните, чтобы изменить ширину"
            className="hidden w-1.5 shrink-0 cursor-col-resize rounded bg-gray-200 hover:bg-brand lg:block"
          />
        )}

        {/* Правая колонка — постоянный чат с агентом */}
        {chatVisible && (
          <section
            style={isDesktop ? { width: chatWidth } : undefined}
            className="flex w-full shrink-0 flex-col rounded-xl border bg-white p-4 shadow-sm lg:min-h-0"
          >
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-brand-dark">{t("nutritionist.chat")}</h2>
              <button
                onClick={toggleChat}
                className="rounded-md border px-2 py-1 text-xs text-gray-600 hover:bg-brand-light"
              >
                {t("nutritionist.hide_chat")} ›
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <NutritionistChat onView={handleView} onAnalysis={setAnalysis} />
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
