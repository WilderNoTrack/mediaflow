import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAdminUnlock, useMe } from "../api/hooks";
import { Button, ErrorText, Input, Label, Logo } from "../components/ui";

/** 演示版的管理员入口：/admin 输入口令，这个浏览器就能填 Key、连平台（记住 30 天）。页面上不放入口链接。 */
export function AdminPage() {
  const { data: me } = useMe();
  const { unlock, lock } = useAdminUnlock();
  const [token, setToken] = useState("");
  const demo = me?.auth === "demo";
  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-slate-50 via-white to-indigo-50 p-4">
      <div className="w-full max-w-sm space-y-5 rounded-2xl border-2 bg-card p-6 shadow-xl shadow-indigo-500/5">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="font-bold">管理员入口</div>
            <div className="text-xs text-muted-foreground">填 Key、连平台这些设置要先输口令</div>
          </div>
        </div>
        {!demo ? (
          <p className="text-sm text-muted-foreground">现在不是演示版，不需要口令。</p>
        ) : me?.is_admin ? (
          <div className="space-y-3">
            <p className="flex items-center gap-2 text-sm text-emerald-700"><ShieldCheck className="size-4" />这个浏览器已经是管理员了，首页能看到所有设置。</p>
            <Button variant="outline" className="w-full" loading={lock.isPending} onClick={() => lock.mutate()}>退出管理员</Button>
          </div>
        ) : (
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (token.trim()) unlock.mutate(token.trim()); }}>
            <div><Label>管理员口令</Label><Input type="password" autoFocus autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} /></div>
            <ErrorText error={unlock.error} />
            <Button type="submit" variant="gradient" className="w-full" loading={unlock.isPending} disabled={!token.trim()}>进入管理</Button>
          </form>
        )}
        <Link to="/" className="block text-center text-xs text-indigo-600 hover:underline">回首页</Link>
      </div>
    </div>
  );
}
