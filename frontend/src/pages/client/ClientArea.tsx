import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { supabase } from "../../lib/supabase";
import { useAuth } from "../../auth/AuthProvider";
import { api } from "../../lib/api";
import { ConsentGate } from "../../features/consent/ConsentGate";
import { Questionnaire } from "../../features/questionnaire/Questionnaire";
import { ClientShell } from "./ClientShell";

/**
 * Точка входа кабинета клиента. Два блокирующих гейта, по порядку:
 * 1. Согласие на обработку данных (LEGAL-1, миграция 018) — пока нет согласия с текущей
 *    версией текста (client_consents.consent_version !== актуальная версия) — показываем
 *    ConsentGate. Версия меняется — согласие запрашивается заново.
 * 2. Анкета онбординга — пока не заполнена (client_profiles.onboarding_completed_at IS NULL).
 */
export function ClientArea() {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  const clientId = appUser?.client_id ?? null;

  const consentText = useQuery({
    queryKey: ["consent_text"],
    queryFn: () => api.consentText(),
  });

  const consentStatus = useQuery({
    queryKey: ["consent_status", clientId],
    enabled: !!clientId,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("client_consents")
        .select("consent_version")
        .eq("client_id", clientId!)
        .order("accepted_at", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });

  const onboarding = useQuery({
    queryKey: ["onboarding", clientId],
    enabled: !!clientId,
    queryFn: async () => {
      const { data, error } = await supabase
        .from("client_profiles")
        .select("onboarding_completed_at")
        .eq("client_id", clientId!)
        .maybeSingle();
      if (error) throw error;
      return data;
    },
  });

  if (!clientId) return <div className="p-8 text-gray-500">{t("loading")}</div>;
  if (consentText.isLoading || consentStatus.isLoading || onboarding.isLoading) {
    return <div className="p-8 text-gray-500">{t("loading")}</div>;
  }

  const needsConsent = consentStatus.data?.consent_version !== consentText.data?.version;
  if (needsConsent) {
    return <ConsentGate onDone={() => consentStatus.refetch()} />;
  }

  const completed = !!onboarding.data?.onboarding_completed_at;
  if (!completed) {
    return <Questionnaire clientId={clientId} onDone={() => onboarding.refetch()} />;
  }
  return <ClientShell />;
}
