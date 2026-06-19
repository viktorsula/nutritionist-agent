import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { supabase } from "../../lib/supabase";
import { useAuth } from "../../auth/AuthProvider";
import { Questionnaire } from "../../features/questionnaire/Questionnaire";
import { ClientShell } from "./ClientShell";

/**
 * Точка входа кабинета клиента. Gate онбординга: пока опросник не заполнен
 * (client_profiles.onboarding_completed_at IS NULL) — показываем форму.
 */
export function ClientArea() {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  const clientId = appUser?.client_id ?? null;

  const { data, isLoading, refetch } = useQuery({
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
  if (isLoading) return <div className="p-8 text-gray-500">{t("loading")}</div>;

  const completed = !!data?.onboarding_completed_at;
  if (!completed) {
    return <Questionnaire clientId={clientId} onDone={() => refetch()} />;
  }
  return <ClientShell />;
}
