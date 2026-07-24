import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { CatalogEditor } from "./settings/CatalogEditor";
import { JsonSetting } from "./settings/JsonSetting";
import { TrustedSources } from "./settings/TrustedSources";
import { PromptEditor } from "./settings/PromptEditor";
import { KnowledgeBase } from "./settings/KnowledgeBase";
import { LlmConfigEditor } from "./settings/LlmConfigEditor";

/** Сворачиваемая секция настроек. */
function Section({ title, children, open = false }: { title: string; children: ReactNode; open?: boolean }) {
  return (
    <details open={open} className="rounded-md border bg-white">
      <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-brand-dark">
        {title}
      </summary>
      <div className="border-t p-3">{children}</div>
    </details>
  );
}

/**
 * Настройки нутрициолога (перенос со Streamlit): каталог показателей, пороги
 * алертов, доверенные источники, LLM-модели, редактор промптов.
 * Пороги/источники/llm — system_settings под RLS; промпты — через бэкенд.
 */
export function SettingsPanel() {
  const { t } = useTranslation();

  return (
    <div className="max-w-3xl space-y-3">
      <Section title={t("settings.catalog.title")} open>
        <CatalogEditor />
      </Section>

      <Section title={t("settings.thresholds.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.thresholds.hint")}</p>
        <JsonSetting settingKey="alert_thresholds" hint='{"glucose_critical": 15, "glucose_high": 10}' />
      </Section>

      <Section title={t("settings.sources.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.sources.hint")}</p>
        <TrustedSources />
      </Section>

      <Section title={t("settings.consent.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.consent.hint")}</p>
        <JsonSetting
          settingKey="consent_text"
          hint='{"version": "1.1", "ru": {"health_data": "...", "telegram_channel": "..."}, "en": {...}}'
        />
      </Section>

      <Section title={t("settings.knowledge.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.knowledge.hint")}</p>
        <KnowledgeBase />
      </Section>

      <Section title={t("settings.llm.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.llm.hint")}</p>
        <LlmConfigEditor />
      </Section>

      <Section title={t("settings.prompts.title")}>
        <p className="mb-2 text-xs text-gray-500">{t("settings.prompts.hint")}</p>
        <PromptEditor />
      </Section>
    </div>
  );
}
