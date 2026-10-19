import { useQueryClient } from "@tanstack/react-query";
import qrcode from "qrcode-generator";
import { QrCode, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, unwrap } from "../api/client";
import { cn } from "../lib/utils";
import { Button, ErrorText } from "./ui";

type Platform = "bilibili" | "xiaohongshu";

const LABEL: Record<string, string> = {
  scanned: "已扫码，请在手机上点「确认登录」",
  expired: "二维码过期了，点刷新重新生成",
  error: "登录没成功",
};
const WAITING: Record<Platform, string> = {
  bilibili: "用 B站 App 扫一扫（「我的」右上角）",
  xiaohongshu: "打开小红书 App，点左上角「≡」→「扫一扫」，扫完在手机上点「确认登录」。建议用小号",
};
const OK: Record<Platform, string> = {
  bilibili: "登录成功，已开启自动续期",
  xiaohongshu: "登录成功，可以搜小红书了",
};

const create = (p: Platform) =>
  p === "bilibili" ? unwrap(api.POST("/api/settings/bilibili/qrcode")) : unwrap(api.POST("/api/settings/xiaohongshu/qrcode"));
const poll = (p: Platform, key: string) => {
  const params = { params: { path: { key } } };
  return p === "bilibili"
    ? unwrap(api.GET("/api/settings/bilibili/qrcode/{key}", params))
    : unwrap(api.GET("/api/settings/xiaohongshu/qrcode/{key}", params));
};

/** 扫码登录：B站会拿到 refresh_token，后端每天自动续期；小红书登录后用于笔记搜索 */
export function QrLogin({ platform, again = false }: { platform: Platform; again?: boolean }) {
  const qc = useQueryClient();
  const [qr, setQr] = useState<{ url: string; key: string } | null>(null);
  const [status, setStatus] = useState("waiting");
  const [message, setMessage] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const start = async () => {
    setLoading(true); setError(null); setStatus("waiting"); setMessage("");
    try { setQr(await create(platform)); } catch (e) { setError(e); } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!qr || status === "ok" || status === "expired" || status === "error") return;
    const t = setInterval(async () => {
      try {
        const r = await poll(platform, qr.key);
        setStatus(r.status);
        setMessage(r.message ?? "");
        setError(null);
        if (r.status === "ok") qc.invalidateQueries({ queryKey: ["credentials"] });
      } catch (e) { setError(e); } // 偶发网络错误：显示出来，但继续轮询
    }, 2000);
    return () => clearInterval(t);
  }, [qr, status, qc, platform]);

  const svg = useMemo(() => {
    if (!qr) return "";
    // 纠错级别用 L：同样的链接码点更少、每个点更大，手机更容易扫上
    const q = qrcode(0, "L");
    q.addData(qr.url);
    q.make();
    return q.createSvgTag({ cellSize: 6, margin: 4, scalable: true });
  }, [qr]);

  if (!qr) {
    return <Button size="sm" variant="outline" loading={loading} onClick={start}>{!loading && <QrCode />}{again ? "重新扫码登录" : "扫码登录"}</Button>;
  }
  const bad = status === "expired" || status === "error";
  return (
    <div className="flex flex-col items-center gap-4 rounded-lg bg-slate-50 p-4 sm:flex-row sm:items-start">
      <div className={cn("relative size-48 shrink-0 rounded-lg bg-white p-1 shadow-sm [&_svg]:size-full", bad && "opacity-30")}
        dangerouslySetInnerHTML={{ __html: svg }} />
      <div className="min-w-0 space-y-2 text-sm">
        <div className={status === "ok" ? "font-medium text-emerald-600" : bad ? "font-medium text-red-500" : status === "scanned" ? "font-medium text-indigo-600" : "text-muted-foreground"}>
          {status === "waiting" ? WAITING[platform] : status === "ok" ? OK[platform] : LABEL[status] ?? status}
        </div>
        {message && <p className="text-xs leading-relaxed text-red-500">{message}</p>}
        {platform === "xiaohongshu" && bad && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            也可以手动连：电脑浏览器打开 xiaohongshu.com 并登录 → 按 F12 打开「网络 / Network」→ 刷新页面 → 点任意一个请求 →
            在「请求标头」里把 Cookie 整段复制，粘贴到下面的输入框保存。
          </p>
        )}
        {status !== "ok" && <Button size="sm" variant={bad ? "outline" : "ghost"} onClick={start}><RefreshCw />刷新二维码</Button>}
        <ErrorText error={error} />
      </div>
    </div>
  );
}
