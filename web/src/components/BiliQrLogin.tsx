import { useQueryClient } from "@tanstack/react-query";
import qrcode from "qrcode-generator";
import { QrCode, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, ErrorText } from "./ui";

const LABEL: Record<string, string> = {
  waiting: "用 B站 App 扫一扫（「我的」右上角）",
  scanned: "已扫码，请在手机上点「确认登录」",
  expired: "二维码过期了，点刷新重新生成",
  ok: "登录成功，已开启自动续期",
  error: "登录出错了，刷新重试",
};

/** B站扫码登录：拿到 refresh_token，后端每天自动续期 Cookie */
export function BiliQrLogin() {
  const qc = useQueryClient();
  const [qr, setQr] = useState<{ url: string; key: string } | null>(null);
  const [status, setStatus] = useState("waiting");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const start = async () => {
    setLoading(true); setError(null); setStatus("waiting");
    try { setQr(await unwrap(api.POST("/api/settings/bilibili/qrcode"))); } catch (e) { setError(e); } finally { setLoading(false); }
  };

  useEffect(() => {
    if (!qr || status === "ok" || status === "expired" || status === "error") return;
    const t = setInterval(async () => {
      try {
        const r = await unwrap(api.GET("/api/settings/bilibili/qrcode/{key}", { params: { path: { key: qr.key } } }));
        setStatus(r.status);
        if (r.status === "ok") qc.invalidateQueries({ queryKey: ["credentials"] });
      } catch (e) { setError(e); }
    }, 2000);
    return () => clearInterval(t);
  }, [qr, status, qc]);

  const svg = useMemo(() => {
    if (!qr) return "";
    const q = qrcode(0, "M");
    q.addData(qr.url);
    q.make();
    return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  }, [qr]);

  if (!qr) {
    return <Button size="sm" variant="outline" loading={loading} onClick={start}>{!loading && <QrCode />}扫码登录</Button>;
  }
  return (
    <div className="flex items-center gap-4 rounded-lg bg-slate-50 p-3">
      <div className="size-32 shrink-0 bg-white" dangerouslySetInnerHTML={{ __html: svg }} />
      <div className="space-y-2 text-xs">
        <div className={status === "ok" ? "font-medium text-emerald-600" : status === "expired" || status === "error" ? "text-red-500" : "text-muted-foreground"}>
          {LABEL[status] ?? status}
        </div>
        {status !== "ok" && <Button size="sm" variant="ghost" onClick={start}><RefreshCw />刷新二维码</Button>}
        <ErrorText error={error} />
      </div>
    </div>
  );
}
