import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/Button";
import type { CenterView, AgentAnalysis } from "./view";

interface Msg {
  role: "user" | "agent";
  text: string;
}

/**
 * Чат нутрициолога с агентом (аналитика + управление через /nutritionist/query).
 * Действия записи выполняются с двухшаговым подтверждением: агент просит подтвердить,
 * нутрициолог отвечает «да»/«нет» (pending_action хранится на бэке по nutritionist_id).
 * История — в рамках сессии (не грузится из БД).
 */
export function NutritionistChat({
  onView,
  onAnalysis,
}: {
  onView?: (view: CenterView) => void;
  onAnalysis?: (analysis: AgentAnalysis) => void;
}) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  function autoResize() {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }
  useEffect(autoResize, [input]);
  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setError("");
    setInput("");
    requestAnimationFrame(autoResize);
    setMessages((m) => [...m, { role: "user", text }]);
    setBusy(true);
    try {
      const res = (await api.nutritionistQuery(text)) as {
        message?: string;
        view?: CenterView | null;
        analysis?: AgentAnalysis | null;
      };
      setMessages((m) => [...m, { role: "agent", text: res.message ?? "…" }]);
      if (res.analysis && onAnalysis) onAnalysis(res.analysis);
      if (res.view && onView) onView(res.view);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("nchat.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-[70vh] flex-col">
      <p className="mb-2 text-xs text-gray-500">{t("nchat.hint")}</p>

      <div className="flex-1 space-y-2 overflow-y-auto rounded-md border bg-gray-50 p-3">
        {messages.length === 0 && (
          <div className="space-y-1 py-6 text-center text-xs text-gray-400">
            <div>{t("nchat.empty")}</div>
            <div className="text-gray-300">{t("nchat.examples")}</div>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
              m.role === "user" ? "ml-auto bg-brand text-white" : "mr-auto bg-white text-gray-800 shadow-sm"
            }`}
          >
            {m.text}
          </div>
        ))}
        {busy && <div className="text-xs text-gray-400">{t("nchat.thinking")}</div>}
        <div ref={endRef} />
      </div>

      {error && <div className="py-1 text-xs text-red-600">{error}</div>}

      <form onSubmit={send} className="mt-2 flex items-end gap-2">
        <textarea
          ref={taRef}
          rows={1}
          className="flex-1 resize-none rounded-md border px-3 py-2 text-sm leading-snug"
          placeholder={t("nchat.placeholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(e as unknown as FormEvent);
            }
          }}
        />
        <Button type="submit" disabled={busy}>
          {t("nchat.send")}
        </Button>
      </form>
    </div>
  );
}
