import type { ReactNode } from "react";

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border bg-white p-4 shadow-sm">
      {title && (
        <h3 className="mb-3 text-sm font-semibold text-brand-dark">{title}</h3>
      )}
      {children}
    </div>
  );
}
