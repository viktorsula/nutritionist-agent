import { useQuery } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { api } from "../../lib/api";

const BUCKET = "client-documents";

/**
 * Безопасное имя для ключа Supabase Storage (только ASCII).
 * Кириллица, пробелы и скобки в ключе вызывают "Invalid key", поэтому
 * чистим имя; оригинал сохраняется в document_metadata.file_name.
 */
export function safeStorageName(name: string): string {
  const dot = name.lastIndexOf(".");
  const ext =
    dot > 0 ? name.slice(dot + 1).toLowerCase().replace(/[^a-z0-9]/g, "") : "";
  const base =
    (dot > 0 ? name.slice(0, dot) : name)
      .replace(/[^a-zA-Z0-9._-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "file";
  return ext ? `${base}.${ext}` : base;
}

function storageKey(clientId: string, file: File): string {
  const rand = Math.random().toString(36).slice(2, 8);
  return `${clientId}/${Date.now()}_${rand}_${safeStorageName(file.name)}`;
}

export interface ClientDocument {
  id: string;
  file_name: string | null;
  mime_type: string | null;
  storage_url: string | null; // путь в Storage
  document_type: string | null;
  metadata: { category?: string; doc_date?: string } | null;
  created_at: string;
}

export function useClientDocuments(clientId: string) {
  return useQuery({
    queryKey: ["client_documents", clientId],
    queryFn: async (): Promise<ClientDocument[]> => {
      const { data, error } = await supabase
        .from("document_metadata")
        .select("id,file_name,mime_type,storage_url,document_type,metadata,created_at")
        .eq("client_id", clientId)
        .order("created_at", { ascending: false });
      if (error) throw error;
      return data ?? [];
    },
  });
}

/** Загружает файлы в Storage + пишет метаданные. Бросает при ошибке Storage. */
export async function uploadDocuments(
  clientId: string,
  files: File[],
  category: string,
  docDate: string,
): Promise<void> {
  for (const file of files) {
    const path = storageKey(clientId, file);
    const up = await supabase.storage.from(BUCKET).upload(path, file);
    if (up.error) throw new Error(up.error.message);

    const meta = await supabase
      .from("document_metadata")
      .insert({
        source: "client_upload",
        client_id: clientId,
        document_type: "client_document",
        file_name: file.name,
        mime_type: file.type || "application/octet-stream",
        storage_url: path,
        file_size_bytes: file.size,
        metadata: { category, doc_date: docDate },
      })
      .select("id")
      .single();
    if (meta.error) throw new Error(meta.error.message);

    // Векторизация контента в client_documents (pgvector) — best-effort:
    // загрузка уже успешна, сбой эмбеддинга не должен ронять весь процесс.
    try {
      await api.ingestDocument(meta.data.id as string);
    } catch (e) {
      console.warn("ingestDocument failed:", e);
    }
  }
}

/** Временная защищённая ссылка на файл (приватный бакет). */
export async function getSignedUrl(path: string): Promise<string | null> {
  const { data, error } = await supabase.storage.from(BUCKET).createSignedUrl(path, 3600);
  if (error) return null;
  return data.signedUrl;
}
