import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { useTranslation } from "react-i18next";
import { supabase } from "../../lib/supabase";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/Button";

interface Msg {
  role: string; // 'client' | 'agent'
  text: string;
}

export function ChatPanel({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Авто-высота textarea под объём текста (с ограничением сверху ~5 строк).
  function autoResize() {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 140)}px`;
  }
  useEffect(autoResize, [input]);

  // История из БД (под RLS — только свои сообщения).
  useEffect(() => {
    (async () => {
      const { data } = await supabase
        .from("conversations")
        .select("role,message_text,created_at")
        .eq("client_id", clientId)
        .order("created_at", { ascending: true })
        .limit(50);
      if (data) {
        setMessages(
          data
            .filter((d) => d.role === "client" || d.role === "agent")
            .map((d) => ({ role: d.role, text: d.message_text })),
        );
      }
    })();
  }, [clientId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setError("");
    setInput("");
    requestAnimationFrame(autoResize); // вернуть поле к одной строке
    setMessages((m) => [...m, { role: "client", text }]);
    setBusy(true);
    try {
      const res = (await api.chat(text)) as { message?: string };
      setMessages((m) => [...m, { role: "agent", text: res.message ?? "…" }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("client.chat_error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <div className="py-8 text-center text-xs text-gray-400">
            {t("client.chat_empty")}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              m.role === "client"
                ? "ml-auto bg-brand text-white"
                : "mr-auto bg-gray-100 text-gray-800"
            }`}
          >
            {m.text}
          </div>
        ))}
        {busy && <div className="text-xs text-gray-400">{t("client.chat_thinking")}</div>}
        <div ref={endRef} />
      </div>

      {error && <div className="py-1 text-xs text-red-600">{error}</div>}

      <form onSubmit={send} className="mt-2 flex items-end gap-2">
        <textarea
          ref={taRef}
          rows={1}
          className="flex-1 resize-none rounded-md border px-3 py-2 text-sm leading-snug"
          placeholder={t("client.chat_placeholder")}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => {
            // Enter — отправить, Shift+Enter — перенос строки.
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(e as unknown as FormEvent);
            }
          }}
        />
        <Button type="submit" disabled={busy}>
          {t("client.chat_send")}
        </Button>
      </form>
    </div>
  );
}
