import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { Header } from "../../components/Header";
import { api } from "../../lib/api";

interface Props {
  onDone: () => void;
}

/**
 * Блокирующий шаг согласия на обработку персональных данных (LEGAL-1, миграция 018) —
 * показывается ДО анкеты онбординга (Federal Law №2/2019 требует согласие ДО сбора данных
 * о здоровье). Три гранулярных пункта, «Продолжить» неактивна, пока не отмечены все три.
 * Гейт в ClientArea.tsx: показывается заново, если версия текста изменилась с последнего
 * согласия клиента.
 */
export function ConsentGate({ onDone }: Props) {
  const { t, i18n } = useTranslation();
  const lang: "ru" | "en" = i18n.resolvedLanguage === "en" ? "en" : "ru";

  const { data, isLoading } = useQuery({
    queryKey: ["consent_text"],
    queryFn: () => api.consentText(),
  });

  const [healthData, setHealthData] = useState(false);
  const [telegramChannel, setTelegramChannel] = useState(false);
  const [crossBorder, setCrossBorder] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const allChecked = healthData && telegramChannel && crossBorder;

  async function submit() {
    if (!allChecked) {
      setError(t("consent.required_error"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api.acceptConsent({
        health_data: healthData,
        telegram_channel: telegramChannel,
        cross_border_transfer: crossBorder,
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : t("consent.submit_error"));
    } finally {
      setBusy(false);
    }
  }

  if (isLoading || !data) {
    return (
      <div className="min-h-screen bg-gray-50">
        <Header />
        <div className="p-8 text-gray-500">{t("loading")}</div>
      </div>
    );
  }

  const texts = data[lang];

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="mx-auto max-w-2xl p-4">
        <div className="rounded-xl bg-white p-6 shadow-sm">
          <h1 className="mb-4 text-lg font-semibold text-brand-dark">{t("consent.title")}</h1>
          <p className="mb-4 text-sm text-gray-600">{t("consent.intro")}</p>

          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={healthData}
                onChange={(e) => setHealthData(e.target.checked)}
              />
              <span>{texts.health_data}</span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={telegramChannel}
                onChange={(e) => setTelegramChannel(e.target.checked)}
              />
              <span>{texts.telegram_channel}</span>
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={crossBorder}
                onChange={(e) => setCrossBorder(e.target.checked)}
              />
              <span>{texts.cross_border_transfer}</span>
            </label>
          </div>

          {error && <div className="mt-4 text-sm text-red-600">{error}</div>}

          <div className="mt-6 flex justify-end">
            <Button onClick={submit} disabled={!allChecked || busy}>
              {busy ? t("consent.submitting") : t("consent.continue")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
