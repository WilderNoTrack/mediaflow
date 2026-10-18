import { Bot, Check, ChevronRight, Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAccounts, useClone, useCreateAccount, useCredentials, useDeleteAccount, useSystem } from "../api/hooks";
import { Header } from "../components/Header";
import { SourcesDialog } from "../components/SourcesDialog";
import { Avatar, Badge, Button, Empty, ErrorText, Input, Label, Logo, Modal, Segmented, Spinner } from "../components/ui";
import { cn, timeAgo } from "../lib/utils";

export function AccountsPage() {
  const { data: accounts = [], isLoading } = useAccounts();
  const create = useCreateAccount();
  const del = useDeleteAccount();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [form, setForm] = useState({ name: "", theme: "" });
  const [mode, setMode] = useState<"blank" | "clone">("blank");
  const [target, setTarget] = useState("");
  const clone = useClone("");
  const openNew = (m: "blank" | "clone") => { setMode(m); setOpen(true); };
  const cloneMode = mode === "clone";
  const canCreate = !!form.name.trim() && (!cloneMode || (!!target.trim() && !!form.theme.trim()));
  const submit = () => create.mutate({ ...form, audience: "" }, {
    onSuccess: (a) => {
      if (!cloneMode) return nav(`/accounts/${a.id}?tab=config`);
      clone.mutate({ accountId: a.id, target: target.trim(), theme: form.theme.trim(), platform: "xiaohongshu" },
        { onSettled: () => nav(`/accounts/${a.id}?tab=bench`) });
    },
  });

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
        <Setup onSources={() => setSourcesOpen(true)} />

        <div className="mb-8 flex items-end justify-between">
          <div>
            <h1 className="mb-1 text-2xl font-bold">我的账号</h1>
            <p className="text-sm text-muted-foreground">每个账号是一条独立的内容赛道，点进去开始孵化</p>
          </div>
          {accounts.length > 0 && (
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => openNew("clone")}><Copy />复刻一个账号</Button>
              <Button variant="gradient" onClick={() => openNew("blank")}><Plus />新建账号</Button>
            </div>
          )}
        </div>

        {isLoading ? (
          <div className="flex justify-center py-20"><Spinner className="size-6" /></div>
        ) : accounts.length === 0 ? (
          <Empty
            title="还没有账号"
            desc="从零起一个，或者找个做起来的小红书博主照着复刻，只换成你的主题。"
            action={<div className="flex gap-2">
              <Button variant="outline" onClick={() => openNew("clone")}><Copy />复刻对标账号</Button>
              <Button variant="gradient" onClick={() => openNew("blank")}><Plus />新建第一个账号</Button>
            </div>}
          />
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {accounts.map((a) => (
              <div
                key={a.id}
                onClick={() => nav(`/accounts/${a.id}`)}
                className="group relative flex cursor-pointer flex-col rounded-xl border-2 bg-card p-5 transition-all hover:border-indigo-300 hover:shadow-lg"
              >
                <div className="mb-3 flex items-center gap-3">
                  <Avatar name={a.name} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-semibold">{a.name}</div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                      {a.writing ? <span className="flex items-center gap-1 text-indigo-600"><Spinner className="size-3" />正在写稿</span>
                        : a.auto_enabled ? <span className="flex items-center gap-1 text-emerald-600"><Bot className="size-3" />自动运营中</span>
                        : <span>更新于 {timeAgo(a.updated_at)}</span>}
                    </div>
                  </div>
                </div>
                <p className={cn("mb-4 line-clamp-2 flex-1 text-sm", a.theme ? "text-foreground/80" : "text-muted-foreground")}>
                  {a.theme || "定位还没定，进去跟小媒聊聊"}
                </p>
                <div className="flex items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
                  <span>{a.total_drafts} 篇草稿</span>
                  {a.pending_review > 0 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); nav(`/accounts/${a.id}?tab=contents`); }}
                      className="cursor-pointer rounded-full bg-amber-100 px-2 py-0.5 font-medium text-amber-700 hover:bg-amber-200"
                    >{a.pending_review} 篇待审核</button>
                  )}
                  <ChevronRight className="ml-auto size-4 text-muted-foreground/40 group-hover:text-muted-foreground" />
                </div>
                <button
                  className="absolute right-3 top-3 cursor-pointer rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                  aria-label="删除账号"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm(`删除「${a.name}」及其全部草稿、选题和对话？删了找不回来。`)) del.mutate(a.id);
                  }}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {open && (
        <Modal onClose={() => setOpen(false)}>
          <form className="p-6" onSubmit={(e) => { e.preventDefault(); if (canCreate) submit(); }}>
            <h3 className="mb-1 text-lg font-semibold">新建账号</h3>
            <p className="mb-4 text-sm text-muted-foreground">
              {cloneMode ? "给一个做起来的小红书账号，照着 TA 的打法起号，只换成你的主题" : "起个名字就行，进去后小媒会陪你把定位聊清楚"}
            </p>
            <div className="mb-5">
              <Segmented<"blank" | "clone"> value={mode} onChange={setMode} items={[
                { value: "blank", label: "从零开始", icon: <Plus /> },
                { value: "clone", label: "复刻对标账号", icon: <Copy /> },
              ]} />
            </div>
            <div className="space-y-4">
              <div>
                <Label>账号名称</Label>
                <Input autoFocus value={form.name} placeholder="例如：打工人理财笔记" onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              {cloneMode && (
                <div>
                  <Label hint="主页链接、笔记链接、博主名字或小红书号">对标账号</Label>
                  <Input value={target} placeholder="https://www.xiaohongshu.com/user/profile/…" onChange={(e) => setTarget(e.target.value)} />
                </div>
              )}
              <div>
                <Label hint={cloneMode ? "对方的打法会换到这个主题上" : "可以先不填"}>{cloneMode ? "我想做的主题" : "一句话说说做什么"}</Label>
                <Input value={form.theme} placeholder={cloneMode ? "例如：职场新人理财" : "例如：帮刚工作的年轻人学会存钱"} onChange={(e) => setForm({ ...form, theme: e.target.value })} />
              </div>
              {cloneMode && <p className="text-xs text-muted-foreground">创建后自动拆解（约 1-2 分钟）：读 TA 的爆款 → 拆打法 → 换成你的主题，生成定位、写法规则和复刻选题。需要先在「数据来源」里连上小红书。</p>}
              <ErrorText error={create.error ?? clone.error} />
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>取消</Button>
              <Button type="submit" variant="gradient" disabled={!canCreate} loading={create.isPending || clone.isPending}>
                {cloneMode ? "创建并开始拆解" : "创建并进入"}
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

/** 首次使用的准备清单：缺什么一目了然，全部就绪后自动消失 */
function Setup({ onSources }: { onSources: () => void }) {
  const { data: sys } = useSystem();
  const { data: creds = [] } = useCredentials();
  if (!sys) return null;
  const platforms = new Set(creds.filter((c) => c.configured).map((c) => c.platform));
  const steps = [
    { done: sys.llm_configured, title: "填 DeepSeek API Key", desc: "写稿、对话都靠它。在 server/.env 里填 DEEPSEEK_API_KEY 后重启。", must: true },
    { done: platforms.size >= 2, title: `连接数据来源（已连 ${platforms.size} 个平台）`, desc: "连上小红书、抖音等，选题和对标分析才有真实数据；不连也能用热榜。", action: <Button size="xs" variant="outline" onClick={onSources}>去连接</Button> },
    { done: sys.image_configured, title: "配图服务（可选）", desc: "不配也能用，只是没有自动配图。" },
  ];
  if (steps.every((s) => s.done)) return null;
  return (
    <div className="mb-8 rounded-xl border-2 border-indigo-200 bg-card p-5">
      <div className="mb-3 text-sm font-semibold">开始之前 <span className="font-normal text-muted-foreground">· 完成 {steps.filter((s) => s.done).length}/{steps.length}</span></div>
      <div className="space-y-3">
        {steps.map((s) => (
          <div key={s.title} className="flex items-start gap-3">
            <span className={cn("mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border text-[10px]",
              s.done ? "border-emerald-500 bg-emerald-500 text-white" : s.must ? "border-red-300 text-red-500" : "border-gray-300")}>
              {s.done ? <Check className="size-3" /> : ""}
            </span>
            <div className="min-w-0 flex-1">
              <div className={cn("text-sm", s.done && "text-muted-foreground line-through")}>{s.title}{s.must && !s.done && <Badge className="ml-2 bg-red-50 text-red-600">必需</Badge>}</div>
              {!s.done && <div className="text-xs text-muted-foreground">{s.desc}</div>}
            </div>
            {!s.done && s.action}
          </div>
        ))}
      </div>
    </div>
  );
}
