import { AlertCircle, Bot, KeyRound, CheckCircle2, Clock, FileText, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAccounts, useCreateAccount, useDeleteAccount } from "../api/hooks";
import { Header } from "../components/Header";
import { SourcesDialog } from "../components/SourcesDialog";
import { Avatar, Badge, Button, ErrorText, Input, Label, Logo, Modal, Spinner, Textarea } from "../components/ui";

export function AccountsPage() {
  const { data: accounts = [], isLoading } = useAccounts();
  const create = useCreateAccount();
  const del = useDeleteAccount();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [form, setForm] = useState({ name: "", theme: "", audience: "" });

  return (
    <div className="min-h-full bg-gradient-to-br from-slate-50 via-white to-indigo-50">
      <Header
        left={<>
          <Logo />
          <div>
            <div className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-base font-bold text-transparent">媒力 MediaFlow</div>
            <div className="text-xs text-muted-foreground">账号孵化中台</div>
          </div>
        </>}
        right={<Button variant="outline" size="sm" onClick={() => setSourcesOpen(true)}><KeyRound />数据来源</Button>}
      />
      {sourcesOpen && <SourcesDialog onClose={() => setSourcesOpen(false)} />}

      <div className="container mx-auto max-w-5xl px-6 py-10">
        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="mb-1 text-2xl font-bold">我的账号</h1>
            <p className="text-sm text-muted-foreground">每个账号是一条独立的内容赛道，点进去开始孵化</p>
          </div>
          <Button variant="gradient" onClick={() => setOpen(true)}><Plus />新建账号</Button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-20"><Spinner className="size-6" /></div>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {accounts.map((a) => (
              <div
                key={a.id}
                onClick={() => nav(`/accounts/${a.id}`)}
                className="group relative cursor-pointer rounded-xl border-2 bg-card p-6 transition-all hover:border-indigo-300 hover:shadow-lg"
              >
                <div className="mb-4 flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <Avatar name={a.name} />
                    <div className="min-w-0">
                      <div className="truncate font-medium">{a.name}</div>
                      <div className="text-xs text-muted-foreground">创建于 {new Date(a.created_at).toLocaleDateString("zh-CN")}</div>
                    </div>
                  </div>
                  {a.writing ? <Badge className="bg-indigo-100 text-indigo-700"><Spinner className="size-3" />创作中</Badge>
                    : a.auto_enabled ? <Badge className="bg-green-100 text-green-700"><Bot className="size-3" />自动运营</Badge>
                    : <Badge className="bg-gray-100 text-gray-600">手动</Badge>}
                </div>
                {a.theme ? (
                  <div className="mb-4 flex items-start gap-1.5 text-sm">
                    <Sparkles className="mt-0.5 size-3.5 shrink-0 text-indigo-500" />
                    <span className="line-clamp-2">{a.theme}</span>
                  </div>
                ) : (
                  <div className="mb-4 flex items-center gap-1.5 text-xs text-orange-600">
                    <AlertCircle className="size-3.5" />主题未设定，进入工作台配置
                  </div>
                )}
                <div className="flex items-center gap-4 border-t pt-4 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1"><FileText className="size-3.5" />{a.total_drafts} 篇草稿</span>
                  {a.pending_review > 0
                    ? <span className="flex items-center gap-1 text-amber-600"><Clock className="size-3.5" />{a.pending_review} 篇待审核</span>
                    : <span className="flex items-center gap-1"><CheckCircle2 className="size-3.5 text-green-500" />无待审核</span>}
                </div>
                <button
                  className="absolute bottom-5 right-5 cursor-pointer text-muted-foreground opacity-0 transition-opacity hover:text-red-600 group-hover:opacity-100"
                  aria-label="删除账号"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`删除「${a.name}」及其全部草稿、选题和对话？此操作不可恢复。`)) del.mutate(a.id);
                  }}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
            <button
              onClick={() => setOpen(true)}
              className="flex min-h-[200px] cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed text-muted-foreground transition-all hover:border-indigo-300 hover:text-indigo-500"
            >
              <div className="flex size-12 items-center justify-center rounded-xl border-2 border-dashed"><Plus className="size-5" /></div>
              <span className="text-sm">新建账号</span>
            </button>
          </div>
        )}
      </div>

      {open && (
        <Modal>
          <div className="p-6">
            <h3 className="mb-1 text-lg font-semibold">新建账号</h3>
            <p className="mb-5 text-sm text-muted-foreground">起个名字就行，定位可以进去后和小媒聊着定</p>
            <div className="space-y-4">
              <div>
                <Label>账号名称</Label>
                <Input autoFocus value={form.name} placeholder="例如：打工人理财笔记" onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <Label hint="可选">账号主题</Label>
                <Textarea rows={2} value={form.theme} onChange={(e) => setForm({ ...form, theme: e.target.value })} />
              </div>
              <div>
                <Label hint="可选">目标受众</Label>
                <Input value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} />
              </div>
              <ErrorText error={create.error} />
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>取消</Button>
              <Button
                variant="gradient"
                disabled={!form.name.trim()}
                loading={create.isPending}
                onClick={() => create.mutate(form, { onSuccess: (a) => nav(`/accounts/${a.id}?tab=config`) })}
              >
                创建并进入
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
