import type { ReactNode } from "react";
import { cn } from "../lib/utils";

/** 吸顶顶栏，v1 样式 */
export function Header({ left, right, narrow }: { left: ReactNode; right?: ReactNode; narrow?: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-card/90 shadow-sm backdrop-blur-sm">
      <div className={cn("container mx-auto flex items-center justify-between gap-4 px-6", narrow ? "py-3" : "py-4")}>
        <div className="flex min-w-0 items-center gap-3">{left}</div>
        {right && <div className="flex items-center gap-2">{right}</div>}
      </div>
    </header>
  );
}
