import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

type Job = {
  id: string;
  kind: "content" | "image";
  label: string;
  account_id?: string;
  content_id?: string;
  progress: number | null;
  indeterminate?: boolean;  // 单张重新生成：总数不变，算不出有意义的百分比
  detail: string;
  elapsed_sec?: number;  // 内容创作有真实起始时间
  idle_sec?: number;     // 配图：距上一张落库多久，用来判断是否卡住
};

const POLL_ACTIVE_MS = 3000;   // 有任务时跟得紧一些
const POLL_IDLE_MS = 6000;     // 空闲时放慢，别白耗

/**
 * 页面发起生成后立刻广播，进度条马上查一次。
 * 否则要等下一次空闲轮询（最长 6 秒），用户点完抬头一看什么都没有，
 * 会以为功能坏了。
 */
export const JOB_STARTED_EVENT = "mediaflow:job-started";
export function notifyJobStarted() {
  window.dispatchEvent(new CustomEvent(JOB_STARTED_EVENT));
}

function fmtElapsed(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  return `${m}分${sec % 60}秒`;
}

/**
 * 全局生成进度条。
 *
 * 内容创作和配图生成都是后台异步的，短则十几秒长则几分钟。此前用户只能
 * 停在当前页面干等；这里把进度提到应用外壳上，切页面也不会中断，
 * 用户可以先去干别的，完成时回来看。
 *
 * 进度是真实的：内容创作按 AgentRun 已完成步数算，配图按已落库的
 * 真实图片张数算（后台线程逐张回写）。
 */
export function GenerationProgress() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [justDone, setJustDone] = useState(false);
  const prevCount = useRef(0);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      // 标签页不可见时不轮询，省资源
      if (document.hidden) {
        schedule(POLL_IDLE_MS);
        return;
      }
      const token = localStorage.getItem("token");
      if (!token) {
        schedule(POLL_IDLE_MS);
        return;
      }
      try {
        const res = await fetch(`${API_BASE}/api/workspace/jobs`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok && !cancelled) {
          const data = await res.json();
          const list: Job[] = data.jobs || [];
          // 从「有任务」变成「没任务」= 刚刚全部完成，闪一下完成态
          if (prevCount.current > 0 && list.length === 0) {
            setJustDone(true);
            window.setTimeout(() => setJustDone(false), 2600);
          }
          prevCount.current = list.length;
          setJobs(list);
          schedule(list.length > 0 ? POLL_ACTIVE_MS : POLL_IDLE_MS);
          return;
        }
      } catch {
        // 后端没起来之类，静默退避即可，不打扰用户
      }
      schedule(POLL_IDLE_MS);
    };

    const schedule = (ms: number) => {
      if (cancelled) return;
      timer.current = window.setTimeout(tick, ms);
    };

    tick();

    const kick = () => {
      if (timer.current) window.clearTimeout(timer.current);
      tick();
    };
    const onVisible = () => {
      if (!document.hidden) kick();
    };
    // 页面刚发起生成 -> 立刻查一次，不等下一轮
    window.addEventListener(JOB_STARTED_EVENT, kick);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      if (timer.current) window.clearTimeout(timer.current);
      window.removeEventListener(JOB_STARTED_EVENT, kick);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  if (jobs.length === 0 && !justDone) return null;

  if (justDone) {
    return (
      <div className="fixed top-0 left-0 right-0 z-[100]">
        <div className="h-1 bg-emerald-500 w-full transition-all" />
        <div className="flex justify-center">
          <div className="mt-1 px-3 py-1 rounded-full bg-emerald-500 text-white text-xs shadow-lg">
            ✓ 生成完成
          </div>
        </div>
      </div>
    );
  }

  // 不确定态的任务不参与百分比平均，否则会把总进度算歪
  const measurable = jobs.filter((j) => !j.indeterminate && j.progress != null);
  const allIndeterminate = measurable.length === 0;
  const avg = allIndeterminate
    ? 0
    : measurable.reduce((s, j) => s + (j.progress || 0), 0) / measurable.length;
  const pct = Math.max(3, Math.min(99, Math.round(avg * 100)));
  const headline =
    jobs.length === 1 ? jobs[0].label : `${jobs.length} 个生成任务进行中`;

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] pointer-events-none">
      {/* 顶部细进度条：无法计算百分比时跑一条滚动条，而不是僵在某个数字上 */}
      <div className="h-1 w-full bg-indigo-100 dark:bg-indigo-950 overflow-hidden">
        {allIndeterminate ? (
          <div className="h-full w-1/3 bg-gradient-to-r from-indigo-500 to-fuchsia-500 mf-indeterminate" />
        ) : (
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 transition-[width] duration-700 ease-out"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      <style>{`
        @keyframes mf-slide {
          0%   { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        .mf-indeterminate { animation: mf-slide 1.4s ease-in-out infinite; }
      `}</style>

      {/* 悬浮胶囊：可点开看每个任务 */}
      <div className="flex justify-center">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="pointer-events-auto mt-1.5 px-3 py-1.5 rounded-full bg-background/95 backdrop-blur
                     border shadow-lg text-xs flex items-center gap-2 hover:shadow-xl transition-shadow"
        >
          <span className="w-3 h-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <span className="font-medium">{headline}</span>
          <span className="text-muted-foreground">
            {allIndeterminate ? jobs[0]?.detail ?? "" : `${pct}%`}
          </span>
          <span className="text-muted-foreground">{expanded ? "▴" : "▾"}</span>
        </button>
      </div>

      {expanded && (
        <div className="flex justify-center">
          <div className="pointer-events-auto mt-1.5 w-[min(92vw,420px)] rounded-xl border bg-background/95
                          backdrop-blur shadow-xl p-3 space-y-2.5">
            <p className="text-[11px] text-muted-foreground">
              生成在后台进行，你可以随意切换页面或去忙别的，完成后回来查看即可。
            </p>
            {jobs.map((j) => (
              <div key={j.id} className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate flex-1">
                    <span className="mr-1">{j.kind === "image" ? "🖼️" : "✍️"}</span>
                    {j.label}
                  </span>
                  <span className="text-muted-foreground flex-shrink-0">{j.detail}</span>
                </div>
                <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                  {j.indeterminate || j.progress == null ? (
                    <div
                      className={`h-full w-1/3 rounded-full mf-indeterminate ${
                        j.kind === "image" ? "bg-fuchsia-500" : "bg-indigo-500"
                      }`}
                    />
                  ) : (
                    <div
                      className={`h-full rounded-full transition-[width] duration-700 ${
                        j.kind === "image" ? "bg-fuchsia-500" : "bg-indigo-500"
                      }`}
                      style={{ width: `${Math.max(3, Math.round(j.progress * 100))}%` }}
                    />
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground">
                  {j.kind === "content" && j.elapsed_sec != null
                    ? `已用时 ${fmtElapsed(j.elapsed_sec)}`
                    : j.idle_sec != null && j.idle_sec > 90
                    ? `${fmtElapsed(j.idle_sec)} 没有新进展，可能较慢`
                    : "生成中…"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
