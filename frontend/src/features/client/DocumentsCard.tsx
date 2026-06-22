import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Card } from "../../components/ui/Card";
import { Button } from "../../components/ui/Button";
import {
  useClientDocuments,
  uploadDocuments,
  getSignedUrl,
  type ClientDocument,
} from "./documents";

const CATEGORIES = ["labs", "photo", "doc"] as const;

export function DocumentsCard({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const docs = useClientDocuments(clientId);

  const [category, setCategory] = useState<string>("labs");
  const [docDate, setDocDate] = useState<string>(new Date().toISOString().slice(0, 10));
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload() {
    if (files.length === 0) return;
    setError("");
    setBusy(true);
    try {
      await uploadDocuments(clientId, files, category, docDate);
      setFiles([]);
      await qc.invalidateQueries({ queryKey: ["client_documents", clientId] });
    } catch (e) {
      setError(e instanceof Error ? e.message : t("docs.upload_error"));
    } finally {
      setBusy(false);
    }
  }

  async function open(d: ClientDocument) {
    if (!d.storage_url) return;
    const url = await getSignedUrl(d.storage_url);
    if (url) window.open(url, "_blank", "noopener");
    else setError(t("docs.open_error"));
  }

  const input = "w-full rounded-md border px-2 py-1.5 text-xs";

  return (
    <Card title={t("docs.title")}>
      {/* Загрузка */}
      <div className="space-y-2">
        <div className="flex gap-2">
          <select
            className={input}
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {t(`docs.category.${c}`)}
              </option>
            ))}
          </select>
          <input
            type="date"
            className={input}
            value={docDate}
            onChange={(e) => setDocDate(e.target.value)}
          />
        </div>
        <input
          type="file"
          multiple
          accept="application/pdf,image/*"
          className="text-xs"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <Button onClick={upload} disabled={busy || files.length === 0} className="w-full">
          {busy ? t("docs.uploading") : t("docs.upload")}
        </Button>
        {error && <div className="text-xs text-red-600">{error}</div>}
      </div>

      {/* Список */}
      <div className="mt-3 border-t pt-2">
        {docs.isLoading ? (
          <div className="text-xs text-gray-400">{t("loading")}</div>
        ) : (docs.data ?? []).length === 0 ? (
          <div className="text-xs text-gray-400">{t("docs.empty")}</div>
        ) : (
          <ul className="max-h-48 space-y-1 overflow-y-auto">
            {(docs.data ?? []).map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-2 text-xs">
                <span className="min-w-0">
                  <span className="text-gray-400">
                    {d.metadata?.doc_date || d.created_at.slice(0, 10)}
                  </span>{" "}
                  <span className="text-gray-500">
                    {t(`docs.category.${d.metadata?.category ?? "doc"}`)}
                  </span>{" "}
                  <span className="block truncate font-medium text-gray-800">
                    {d.file_name}
                  </span>
                </span>
                <button
                  onClick={() => open(d)}
                  className="shrink-0 text-brand hover:underline"
                >
                  {t("docs.open")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
