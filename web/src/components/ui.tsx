import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { forwardRef } from "react";
import { cn } from "../lib/utils";

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "gradient" | "outline" | "ghost" | "destructive" | "danger-outline";
  size?: "xs" | "sm" | "md" | "lg";
  loading?: boolean;
};

export function Button({ variant = "default", size = "md", loading, className, children, disabled, ...p }: BtnProps) {
  return (
    <button
      {...p}
      disabled={disabled || loading}
      className={cn(
        "inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium transition-all outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg:not([class*='size-'])]:size-4",
        size === "xs" && "h-7 px-2.5 text-xs [&_svg:not([class*='size-'])]:size-3",
        size === "sm" && "h-8 px-3",
        size === "md" && "h-9 px-4",
        size === "lg" && "h-10 px-6",
        variant === "default" && "bg-primary text-primary-foreground hover:bg-primary/90",
        variant === "gradient" && "bg-gradient-to-r from-indigo-500 to-purple-600 text-white shadow-lg shadow-indigo-500/20 hover:opacity-90",
        variant === "outline" && "border bg-background hover:bg-accent",
        variant === "ghost" && "hover:bg-accent",
        variant === "destructive" && "bg-destructive text-white hover:bg-destructive/90",
        variant === "danger-outline" && "border border-red-200 bg-background text-red-600 hover:bg-red-50",
        className,
      )}
    >
      {loading && <Loader2 className="animate-spin" />}
      {children}
    </button>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input
    ref={ref}
    {...p}
    className={cn(
      "flex h-9 w-full min-w-0 rounded-md border border-transparent bg-input-background px-3 py-1 text-sm outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50",
      className,
    )}
  />
));

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...p }, ref) => (
    <textarea
      ref={ref}
      {...p}
      className={cn(
        "flex min-h-16 w-full rounded-md border border-transparent bg-input-background px-3 py-2 text-sm outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50",
        className,
      )}
    />
  ),
);

export function Card({ className, children, onClick }: { className?: string; children: ReactNode; onClick?: () => void }) {
  return <div onClick={onClick} className={cn("rounded-xl border bg-card shadow-[0_1px_2px_rgba(15,23,42,0.04)]", className)}>{children}</div>;
}

/** 卡片头：小标题 + 可选说明 + 右侧操作 */
export function CardHead({ icon, title, desc, action }: { icon?: ReactNode; title: ReactNode; desc?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 px-5 pt-4">
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-sm font-semibold [&_svg]:size-4 [&_svg]:text-indigo-500">{icon}{title}</div>
        {desc && <div className="mt-1 text-xs text-muted-foreground">{desc}</div>}
      </div>
      {action}
    </div>
  );
}

export const CardBody = ({ className, children }: { className?: string; children: ReactNode }) => (
  <div className={cn("px-5 py-4", className)}>{children}</div>
);

/** 下划线式页签（工作台主导航） */
export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; className?: string;
  items: { value: T; label: ReactNode; icon?: ReactNode; count?: number }[];
}) {
  return (
    <div className={cn("flex items-center gap-1", className)}>
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "relative flex cursor-pointer items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-sm font-medium transition-colors [&_svg]:size-4",
            value === it.value ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {it.icon}{it.label}
          {!!it.count && <span className="rounded-full bg-amber-100 px-1.5 text-[11px] leading-4 text-amber-700">{it.count}</span>}
          {value === it.value && <span className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-indigo-500" />}
        </button>
      ))}
    </div>
  );
}

/** 小号胶囊筛选 */
export function Pills<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn("cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors",
            value === it.value ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted")}
        >{it.label}</button>
      ))}
    </div>
  );
}

export function Badge({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-md border border-transparent px-2 py-0.5 text-xs font-medium whitespace-nowrap", className)}>
      {children}
    </span>
  );
}

export function Switch({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "inline-flex h-[1.15rem] w-8 shrink-0 cursor-pointer items-center rounded-full border border-transparent transition-all disabled:opacity-50",
        checked ? "bg-primary" : "bg-switch-background",
      )}
    >
      <span className={cn("block size-4 rounded-full bg-white transition-transform", checked ? "translate-x-[calc(100%-2px)]" : "translate-x-0")} />
    </button>
  );
}

/** v1 顶栏里的分段式 Tab */
export function Segmented<T extends string>({ value, onChange, items }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode; icon?: ReactNode }[];
}) {
  return (
    <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
      {items.map((it) => (
        <button
          key={it.value}
          onClick={() => onChange(it.value)}
          className={cn(
            "flex cursor-pointer items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all [&_svg]:size-3.5",
            value === it.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {it.icon}{it.label}
        </button>
      ))}
    </div>
  );
}

export const Spinner = ({ className }: { className?: string }) => <Loader2 className={cn("size-4 animate-spin text-indigo-500", className)} />;

export function Empty({ icon, title, desc, action }: { icon?: ReactNode; title: string; desc?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed px-6 py-12 text-center text-muted-foreground">
      {icon && <div className="mx-auto mb-3 w-fit opacity-30 [&_svg]:size-10">{icon}</div>}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {desc && <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed">{desc}</p>}
      {action && <div className="mt-4 flex justify-center gap-2">{action}</div>}
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className="text-sm text-red-600">{error instanceof Error ? error.message : String(error)}</div>;
}

export function Label({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <div className="mb-1.5 text-xs font-medium">
      {children}
      {hint && <span className="ml-1 font-normal text-muted-foreground">（{hint}）</span>}
    </div>
  );
}

export function Modal({ children, className, onClose }: { children: ReactNode; className?: string; onClose?: () => void }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose?.(); }}>
      <div className={cn("w-full max-w-md rounded-2xl bg-card shadow-2xl", className)}>{children}</div>
    </div>
  );
}

/** 品牌标识 */
export const Logo = ({ size = "md" }: { size?: "sm" | "md" }) => (
  <div className={cn(
    "flex items-center justify-center bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg",
    size === "md" ? "size-9 rounded-xl text-xl" : "size-8 rounded-lg text-base",
  )}>🌀</div>
);

export const Avatar = ({ name, size = "md" }: { name: string; size?: "sm" | "md" }) => (
  <div className={cn(
    "flex shrink-0 items-center justify-center bg-gradient-to-br from-indigo-400 to-purple-500 font-bold text-white",
    size === "md" ? "size-12 rounded-xl text-lg" : "size-8 rounded-lg text-sm",
  )}>{(name || "?").slice(0, 1).toUpperCase()}</div>
);
