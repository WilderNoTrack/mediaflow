import { Plus, X } from "lucide-react";
import { useState } from "react";
import { useMe, useUserActions, useUsers } from "../api/hooks";
import { cn } from "../lib/utils";
import { Badge, Button, ErrorText, Input, Modal, Spinner } from "./ui";

const ago = (s?: string | null) => {
  if (!s) return "没登录过";
  const d = new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
  const m = Math.round((Date.now() - d.getTime()) / 60000);
  return m < 60 ? `${Math.max(1, m)} 分钟前` : m < 1440 ? `${Math.round(m / 60)} 小时前` : `${Math.round(m / 1440)} 天前`;
};

/** 成员管理：开账号（把用户名和密码发给 TA）、重置密码、停用。不开放注册。 */
export function UsersDialog({ onClose }: { onClose: () => void }) {
  const { data: users, isLoading } = useUsers();
  const { data: me } = useMe();
  const { add, update } = useUserActions();
  const [form, setForm] = useState({ username: "", name: "", password: "" });
  const [created, setCreated] = useState("");
  const gen = () => setForm((f) => ({ ...f, password: Math.random().toString(36).slice(2, 6) + Math.random().toString(36).slice(2, 8) }));
  return (
    <Modal className="max-w-2xl" onClose={onClose}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <div className="font-semibold">成员管理</div>
          <p className="mt-0.5 text-xs text-muted-foreground">给人开账号后，把用户名和密码发给 TA；每个人的账号、草稿互相看不到。模型 Key 和平台账号大家共用你配的。</p>
        </div>
        <button onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted" aria-label="关闭"><X className="size-4" /></button>
      </div>
      <div className="max-h-[70vh] space-y-5 overflow-y-auto px-5 py-4 text-sm">
        <form className="space-y-2 rounded-xl border-2 border-dashed p-3" onSubmit={(e) => {
          e.preventDefault();
          add.mutate({ ...form, is_admin: false }, { onSuccess: () => { setCreated(`用户名：${form.username}\n密码：${form.password}`); setForm({ username: "", name: "", password: "" }); } });
        }}>
          <div className="font-medium">开一个新账号</div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Input placeholder="用户名（登录用）" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            <Input placeholder="称呼（可选），如 小美" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <div className="flex gap-1">
              <Input placeholder="密码（至少 8 位）" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <Button type="button" size="sm" variant="ghost" onClick={gen}>随机</Button>
            </div>
          </div>
          <ErrorText error={add.error} />
          <div className="flex items-center justify-end">
            <Button type="submit" size="sm" variant="gradient" loading={add.isPending} disabled={!form.username.trim() || form.password.length < 8}><Plus />开账号</Button>
          </div>
          {created && (
            <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
              <div className="mb-1 font-medium">开好了，把下面这段发给 TA：</div>
              <pre className="whitespace-pre-wrap font-sans">{`网址：${location.origin}\n${created}\n登录后可以在右上角改密码`}</pre>
            </div>
          )}
        </form>

        {isLoading ? <Spinner /> : (
          <div className="divide-y rounded-xl border">
            {users?.map((u) => (
              <div key={u.id} className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2.5", u.disabled && "opacity-50")}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 font-medium">
                    {u.name}<span className="text-xs font-normal text-muted-foreground">@{u.username}</span>
                    {u.is_admin && <Badge className="bg-indigo-50 text-indigo-600">管理员</Badge>}
                    {u.disabled && <Badge className="bg-slate-100 text-slate-600">已停用</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {u.accounts} 个号 · {u.drafts} 篇稿 · 今天写了 {(u.usage as { writes?: number }).writes ?? 0} 篇 · {ago(u.last_login_at)}
                  </div>
                </div>
                {u.id !== me?.id && <>
                  <Button size="xs" variant="ghost" onClick={() => {
                    const p = prompt(`给 ${u.name} 设一个新密码（至少 8 位）：`);
                    if (p) update.mutate({ id: u.id, password: p }, { onSuccess: () => alert("已重置，TA 需要用新密码重新登录") });
                  }}>重置密码</Button>
                  <Button size="xs" variant="ghost" className={u.disabled ? "" : "text-red-600"}
                    onClick={() => (u.disabled || confirm(`停用 ${u.name}？TA 会立刻被退出，数据保留，随时可以恢复。`)) && update.mutate({ id: u.id, disabled: !u.disabled })}>
                    {u.disabled ? "恢复" : "停用"}
                  </Button>
                </>}
              </div>
            ))}
          </div>
        )}
        <ErrorText error={update.error} />
      </div>
    </Modal>
  );
}
