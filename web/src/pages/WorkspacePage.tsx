import { ArrowLeft, Copy, FileText, KeyRound, MessageCircle, Settings, TrendingUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { isActive, useAccount, useActiveJobs, useDrafts, useSendChat, useTopics } from "../api/hooks";
import { BenchmarkPanel } from "../components/BenchmarkPanel";
import { ChatPanel } from "../components/ChatPanel";
import { ContentsPanel } from "../components/ContentsPanel";
import { JobStrip } from "../components/JobProgress";
import { SettingsPanel } from "../components/SettingsPanel";
import { SourcesDialog } from "../components/SourcesDialog";
import { TopicsPanel } from "../components/TopicsPanel";
import { Avatar, Button, Empty, Spinner, Tabs } from "../components/ui";

export type Tab = "contents" | "topics" | "bench" | "config";

/** 账号工作台：左边是草稿/选题/设定，右边小媒常驻（手机上是右下角按钮打开的全屏对话）。 */
export function WorkspacePage() {
  const { id = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "contents";
  const setTab = (t: Tab) => setSp({ tab: t });
  const { data: account, isLoading } = useAccount(id);
  const { data: jobs = [] } = useActiveJobs(id);
  const { data: drafts = [] } = useDrafts(id);
  const { data: topics = [] } = useTopics(id);
  const [chatOpen, setChatOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const send = useSendChat(id);
  const started = useRef(false);

  // 新建账号选了「对标起号」：进来就让小媒按主题去找同领域的号
  useEffect(() => {
    if (sp.get("start") !== "bench" || !account || started.current) return;
    started.current = true;
    setSp({ tab: "bench" }, { replace: true });
    if (!account.theme) return;
    send.mutate(`我想对标同领域做得好的小红书账号来起号，主题是「${account.theme}」，帮我找几个看看`);
    if (window.innerWidth < 1024) setChatOpen(true);
  }, [account, sp, setSp, send]);

  if (isLoading) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;
  if (!account) return <div className="p-10"><Empty title="找不到这个账号" action={<Link to="/"><Button size="sm">回到账号列表</Button></Link>} /></div>;

  const writing = jobs.some((j) => j.kind === "write_draft" && isActive(j));
  const pending = drafts.filter((d) => d.status === "pending_review").length;
  const fresh = topics.filter((t) => t.status === "new").length;
  const tabs = (
    <Tabs<Tab>
      value={tab}
      onChange={setTab}
      items={[
        { value: "contents", label: "草稿", icon: <FileText />, count: pending },
        { value: "topics", label: "选题", icon: <TrendingUp />, count: fresh },
        { value: "bench", label: "对标", icon: <Copy /> },
        { value: "config", label: "账号设定", icon: <Settings /> },
      ]}
    />
  );

  return (
    <div className="flex h-full flex-col bg-gradient-to-br from-slate-50 via-white to-indigo-50/40">
      <header className="z-30 shrink-0 border-b bg-card/90 shadow-sm backdrop-blur-sm">
        <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
          <Link to="/"><Button variant="ghost" size="sm"><ArrowLeft /><span className="hidden sm:inline">账号列表</span></Button></Link>
          <div className="flex min-w-0 items-center gap-2">
            <Avatar name={account.name} size="sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{account.name}</div>
              <div className="truncate text-xs text-muted-foreground">{account.theme || "定位还没定"}</div>
            </div>
          </div>
          <div className="ml-auto hidden md:block">{tabs}</div>
          <Button variant="outline" size="sm" className="ml-auto md:ml-2" onClick={() => setSourcesOpen(true)}><KeyRound /><span className="hidden sm:inline">数据来源</span></Button>
        </div>
        <div className="overflow-x-auto px-4 pb-3 md:hidden">{tabs}</div>
      </header>
      {sourcesOpen && <SourcesDialog onClose={() => setSourcesOpen(false)} />}

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
            <JobStrip jobs={jobs} hide={tab === "bench" ? ["clone_creator"] : []} />
            {tab === "contents" && <ContentsPanel account={account} busy={writing} onGoTopics={() => setTab("topics")} />}
            {tab === "topics" && <TopicsPanel account={account} busy={writing} onGoConfig={() => setTab("config")} />}
            {tab === "bench" && <BenchmarkPanel account={account} jobs={jobs} onGoTopics={() => setTab("topics")} onOpenChat={() => setChatOpen(true)} />}
            {tab === "config" && <SettingsPanel account={account} busy={writing} />}
          </div>
        </main>
        <aside className="hidden w-[380px] shrink-0 py-6 pr-6 lg:flex xl:w-[420px]">
          <div className="flex min-h-0 w-full overflow-hidden rounded-xl border-2 bg-card">
            <ChatPanel account={account} />
          </div>
        </aside>
      </div>

      {/* 窄屏：小媒收进右下角按钮 */}
      <button
        onClick={() => setChatOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex cursor-pointer items-center gap-2 rounded-full bg-gradient-to-r from-indigo-500 to-purple-600 px-4 py-3 text-sm font-medium text-white shadow-lg shadow-indigo-500/30 lg:hidden"
      >
        <MessageCircle className="size-4" />问小媒
      </button>
      {chatOpen && (
        <div className="fixed inset-0 z-[90] flex bg-black/30 lg:hidden" onClick={() => setChatOpen(false)}>
          <div className="ml-auto h-full w-full max-w-md shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <ChatPanel account={account} onClose={() => setChatOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
