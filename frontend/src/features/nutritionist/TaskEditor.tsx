import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { supabase } from "../../lib/supabase";
import { Button } from "../../components/ui/Button";
import { useClientTasks } from "./queries";

/** Редактор задач клиента: список + создание + смена статуса. */
export function TaskEditor({ clientId }: { clientId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const tasks = useClientTasks(clientId);

  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["client_tasks", clientId] });

  async function create(e: FormEvent) {
    e.preventDefault();
    const ttl = title.trim();
    if (!ttl || busy) return;
    setBusy(true);
    setError("");
    const { error: err } = await supabase.from("tasks").insert({
      client_id: clientId,
      title: ttl,
      description: desc.trim() || null,
      due_date: due || null,
      status: "pending",
      created_by: "nutritionist",
    });
    setBusy(false);
    if (err) {
      setError(err.message);
      return;
    }
    setTitle("");
    setDue("");
    setDesc("");
    invalidate();
  }

  async function setStatus(id: string, status: "completed" | "cancelled") {
    const patch: Record<string, unknown> = { status };
    if (status === "completed") patch.completed_at = new Date().toISOString();
    const { error: err } = await supabase.from("tasks").update(patch).eq("id", id);
    if (!err) invalidate();
  }

  const input = "rounded-md border px-2 py-1 text-sm";

  return (
    <div className="space-y-3">
      {(tasks.data ?? []).length === 0 ? (
        <div className="text-xs text-gray-400">{t("card.no_tasks")}</div>
      ) : (
        <ul className="space-y-1">
          {(tasks.data ?? []).map((tk) => (
            <li key={tk.id} className="flex items-center justify-between gap-2 text-xs">
              <span className={tk.status === "pending" ? "text-gray-800" : "text-gray-400 line-through"}>
                {tk.title}
                {tk.due_date ? ` · ${tk.due_date.slice(0, 10)}` : ""}
              </span>
              {tk.status === "pending" ? (
                <span className="flex gap-2">
                  <button className="text-green-600 hover:underline" onClick={() => setStatus(tk.id, "completed")}>
                    {t("tasks.done")}
                  </button>
                  <button className="text-red-600 hover:underline" onClick={() => setStatus(tk.id, "cancelled")}>
                    {t("tasks.cancel")}
                  </button>
                </span>
              ) : (
                <span className="text-gray-400">{tk.status}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <form onSubmit={create} className="space-y-2 border-t pt-3">
        <div className="flex flex-wrap gap-2">
          <input
            className={`${input} flex-1`}
            placeholder={t("tasks.title")}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input type="date" className={input} value={due} onChange={(e) => setDue(e.target.value)} />
        </div>
        <input
          className={`${input} w-full`}
          placeholder={t("tasks.desc")}
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
        />
        {error && <div className="text-xs text-red-600">{error}</div>}
        <Button type="submit" disabled={busy}>
          {busy ? t("tasks.adding") : t("tasks.add")}
        </Button>
      </form>
    </div>
  );
}
