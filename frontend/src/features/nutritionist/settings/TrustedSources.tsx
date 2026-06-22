import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../../../auth/AuthProvider";
import { Button } from "../../../components/ui/Button";
import { readSetting, saveSetting } from "./settingsApi";

interface Source {
  name?: string | null;
  url: string;
}

const KEY = "trusted_sources";

/** Доверенные источники (whitelist доменов для веб-поиска): список + добавление/удаление. */
export function TrustedSources() {
  const { t } = useTranslation();
  const { appUser } = useAuth();

  const query = useQuery({
    queryKey: ["setting", KEY],
    queryFn: () => readSetting(KEY),
  });

  const [sources, setSources] = useState<Source[]>([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const arr = query.data;
    setSources(Array.isArray(arr) ? (arr as Source[]) : []);
  }, [query.data]);

  async function persist(next: Source[]) {
    setError("");
    try {
      await saveSetting(KEY, next, appUser?.user_id);
      setSources(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.sources.error"));
    }
  }

  function add() {
    if (!url.trim()) {
      setError(t("settings.sources.url_required"));
      return;
    }
    persist([...sources, { name: name.trim() || null, url: url.trim() }]);
    setName("");
    setUrl("");
  }

  if (query.isLoading) return <div className="text-xs text-gray-400">{t("loading")}</div>;

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      {sources.length === 0 ? (
        <div className="text-xs text-gray-400">{t("settings.sources.empty")}</div>
      ) : (
        <ul className="space-y-1 text-xs">
          {sources.map((s, i) => (
            <li key={i} className="flex items-center justify-between gap-2 rounded border px-2 py-1">
              <span className="text-gray-700">
                {s.name ? `${s.name} — ` : ""}
                {s.url}
              </span>
              <button
                onClick={() => persist(sources.filter((_, j) => j !== i))}
                className="shrink-0 text-red-600 hover:underline"
              >
                {t("settings.sources.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          className={input}
          placeholder={t("settings.sources.name")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={`${input} min-w-[12rem] flex-1`}
          placeholder={t("settings.sources.url")}
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
        <Button type="button" onClick={add}>
          {t("settings.sources.add")}
        </Button>
      </div>
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}
