import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "outline";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const styles: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-dark disabled:opacity-50",
  outline: "border border-brand text-brand hover:bg-brand-light disabled:opacity-50",
};

export function Button({ variant = "primary", className = "", ...props }: Props) {
  return (
    <button
      className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${styles[variant]} ${className}`}
      {...props}
    />
  );
}
