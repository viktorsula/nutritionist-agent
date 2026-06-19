import { useTranslation } from "react-i18next";
import { useAuth } from "../../auth/AuthProvider";
import { Card } from "../../components/ui/Card";
import { useClientProfile, useWellnessPlan, useActivePlan } from "./queries";
import { DocumentsCard } from "./DocumentsCard";

function age(birth?: string | null): number | null {
  if (!birth) return null;
  const d = new Date(birth);
  if (Number.isNaN(d.getTime())) return null;
  const diff = Date.now() - d.getTime();
  return Math.floor(diff / (365.25 * 24 * 3600 * 1000));
}

export function DashboardPanel({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  const profile = useClientProfile(clientId);
  const wellness = useWellnessPlan(clientId);
  const plan = useActivePlan(clientId);

  const p = profile.data;
  const w = wellness.data;
  const tier = appUser?.tier ?? "basic";
  const dash = "—";

  const row = (label: string, value: React.ReactNode) => (
    <div className="flex justify-between gap-2 py-0.5 text-xs">
      <span className="text-gray-500">{label}</span>
      <span className="text-right font-medium text-gray-800">{value || dash}</span>
    </div>
  );

  return (
    <div className="space-y-4">
      <Card title={t("client.profile_title")}>
        <div className="mb-2 text-sm font-semibold text-gray-800">
          {appUser?.name || dash}
        </div>
        {row(
          t("client.status"),
          <span title={t(`client.tier_desc.${tier}`)}>{t(`client.tier.${tier}`)}</span>,
        )}
        {row(t("client.age"), age(p?.birth_date) ?? dash)}
        {row(t("client.current_weight"), p?.weight ? `${p.weight} кг` : dash)}
        {row(t("client.target_weight"), p?.target_weight ? `${p.target_weight} кг` : dash)}
        {row(t("client.goal"), p?.goals)}
      </Card>

      <Card title={t("client.recommendations")}>
        {plan.data?.title ? (
          <div className="mb-2 text-xs">
            <span className="text-gray-500">{t("client.active_plan")}: </span>
            <span className="font-medium text-gray-800">{plan.data.title}</span>
          </div>
        ) : (
          <div className="mb-2 text-xs text-gray-400">{t("client.no_plan")}</div>
        )}

        <div className="text-xs font-medium text-gray-600">{t("client.wellness")}</div>
        {w ? (
          <div className="mt-1 space-y-0.5">
            {row(t("client.sleep"), w.sleep_target)}
            {row(t("client.activity"), w.activity_target)}
            {row(t("client.recovery"), w.recovery)}
            {row(t("client.stress"), w.stress_management)}
          </div>
        ) : (
          <div className="mt-1 text-xs text-gray-400">{t("client.no_data")}</div>
        )}
      </Card>

      <DocumentsCard clientId={clientId} />
    </div>
  );
}
