import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../lib/utils";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
};

export function Button({ variant = "secondary", size = "md", loading, className, children, disabled, ...p }: BtnProps) {
  return (
    <button
      {...p}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4 text-sm",
        variant === "primary" && "bg-brand text-white hover:bg-brand/90",
        variant === "secondary" && "border border-line bg-white hover:bg-surface",
        variant === "ghost" && "hover:bg-black/5",
        variant === "danger" && "text-red-600 hover:bg-red-50",
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input
    ref={ref}
    {...p}
    className={cn("h-10 w-full rounded-lg border border-line bg-white px-3 text-sm outline-none focus:border-brand", className)}
  />
));

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => (
    <textarea
      ref={ref}
      {...p}
      className={cn("w-full rounded-lg border border-line bg-white p-3 text-sm outline-none focus:border-brand", className)}
    />
  ),
);

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-xl border border-line bg-white", className)}>{children}</div>;
}

const TONES = {
  brand: "bg-brand-soft text-brand",
  green: "bg-emerald-50 text-emerald-700",
  gray: "bg-black/5 text-muted",
  amber: "bg-amber-50 text-amber-700",
  red: "bg-red-50 text-red-600",
};

export function Badge({ tone = "gray", children, className }: { tone?: keyof typeof TONES; children: ReactNode; className?: string }) {
  return <span className={cn("inline-flex items-center rounded-md px-1.5 py-0.5 text-xs", TONES[tone], className)}>{children}</span>;
}

export function Tabs<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="flex gap-1 border-b border-line px-4">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "-mb-px cursor-pointer border-b-2 px-3 py-2.5 text-sm",
            value === it.value ? "border-brand font-medium text-ink" : "border-transparent text-muted hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export const Spinner = ({ className }: { className?: string }) => <Loader2 className={cn("size-4 animate-spin text-muted", className)} />;

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center">
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-sm text-sm text-muted">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="text-sm text-red-600">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <div className="text-sm font-medium">{label}</div>
      {children}
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </label>
  );
}
