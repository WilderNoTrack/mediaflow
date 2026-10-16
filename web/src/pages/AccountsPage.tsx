import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAccounts, useCreateAccount, useDeleteAccount } from "../api/hooks";
import { Badge, Button, Card, Empty, ErrorText, Field, Input, Spinner, Textarea } from "../components/ui";

export function AccountsPage() {
  const { data: accounts = [], isLoading } = useAccounts();
  const create = useCreateAccount();
  const del = useDeleteAccount();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", theme: "", audience: "" });

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">我的账号</h1>
          <div className="text-sm text-muted">每个小红书号有独立的定位、规矩、选题库和草稿</div>
        </div>
        <Button variant="primary" onClick={() => setOpen(!open)}><Plus className="size-4" />新建账号</Button>
      </div>

      {open && (
        <Card className="space-y-3 p-4">
          <Field label="账号名"><Input autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="例如：打工人理财笔记" /></Field>
          <Field label="主题定位（可选）" hint="不确定也没关系，建好后和管家聊着定">
            <Textarea rows={2} value={form.theme} onChange={(e) => setForm({ ...form, theme: e.target.value })} />
          </Field>
          <Field label="目标人群（可选）"><Input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} /></Field>
          <ErrorText error={create.error} />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>取消</Button>
            <Button
              variant="primary"
              disabled={!form.name.trim()}
              loading={create.isPending}
              onClick={() => create.mutate(form, { onSuccess: (a) => nav(`/accounts/${a.id}`) })}
            >
              创建并进入
            </Button>
          </div>
        </Card>
      )}

      {isLoading ? <Spinner /> : accounts.length === 0 ? (
        <Card><Empty title="还没有账号" hint="先建一个账号，再和管家聊聊它的定位。" action={<Button variant="primary" onClick={() => setOpen(true)}>新建账号</Button>} /></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((a) => (
            <Card key={a.id} className="group relative p-4 transition-shadow hover:shadow-md">
              <Link to={`/accounts/${a.id}`} className="block space-y-2">
                <div className="flex items-center gap-2">
                  <div className="flex size-9 items-center justify-center rounded-full bg-brand-soft font-semibold text-brand">{a.name.slice(0, 1)}</div>
                  <div className="font-medium">{a.name}</div>
                </div>
                <div className="line-clamp-2 min-h-10 text-sm text-muted">{a.theme || "还没设定位"}</div>
                <div className="flex flex-wrap gap-1.5">
                  {a.pending_review > 0 && <Badge tone="amber">{a.pending_review} 篇待审核</Badge>}
                  <Badge>{a.total_drafts} 篇草稿</Badge>
                  {a.auto_enabled && <Badge tone="green">自动模式</Badge>}
                  {a.writing && <Badge tone="brand">写稿中…</Badge>}
                </div>
              </Link>
              <button
                className="absolute right-3 top-3 cursor-pointer text-muted opacity-0 group-hover:opacity-100 hover:text-red-600"
                aria-label="删除账号"
                onClick={() => { if (confirm(`删除「${a.name}」及其全部草稿、选题和对话？此操作不可恢复。`)) del.mutate(a.id); }}
              >
                <Trash2 className="size-4" />
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
