import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../../components/ui/Button";
import { api } from "../../../lib/api";

const QKEY = ["knowledge_documents"];

/**
 * База знаний нутрициолога: загрузка трудов/методичек (PDF/текст) в knowledge_base
 * (pgvector) + список с удалением. Файл уходит на бэкенд (multipart), там
 * извлекается текст, режется на чанки и эмбеддится — потом доступен агентам.
 */
export function KnowledgeBase() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const query = useQuery({
    queryKey: QKEY,
    queryFn: async () => (await api.knowledgeList()).documents,
  });

  async function onUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    setInfo("");
    try {
      const res = await api.knowledgeUpload(file, title);
      setInfo(`${t("settings.knowledge.uploaded")}: ${res.title} (${res.chunks} ${t("settings.knowledge.chunks")})`);
      setTitle("");
      if (fileRef.current) fileRef.current.value = "";
      await qc.invalidateQueries({ queryKey: QKEY });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.knowledge.upload_error"));
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(id: string) {
    setError("");
    try {
      await api.knowledgeDelete(id);
      await qc.invalidateQueries({ queryKey: QKEY });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("settings.knowledge.remove_error"));
    }
  }

  const docs = query.data ?? [];
  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      {query.isLoading ? (
        <div className="text-xs text-gray-400">{t("loading")}</div>
      ) : docs.length === 0 ? (
        <div className="text-xs text-gray-400">{t("settings.knowledge.empty")}</div>
      ) : (
        <ul className="space-y-1 text-xs">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 rounded border px-2 py-1">
              <span className="text-gray-700">{d.title || d.file_name}</span>
              <button
                onClick={() => onRemove(d.id)}
                className="shrink-0 text-red-600 hover:underline"
              >
                {t("settings.knowledge.remove")}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <input
          className={input}
          placeholder={t("settings.knowledge.title_label")}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <input ref={fileRef} type="file" accept=".pdf,.txt,.md,text/plain,application/pdf" className="text-xs" />
        <Button type="button" onClick={onUpload} disabled={busy}>
          {busy ? t("settings.knowledge.uploading") : t("settings.knowledge.upload")}
        </Button>
      </div>

      {info && <div className="text-xs text-green-700">{info}</div>}
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}
