import { ArrowLeft, FileText, KeyRound, MessageCircle, Settings2, TrendingUp } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { isActive, useAccount, useActiveJobs, useDrafts, useTopics } from "../api/hooks";
import { ChatPanel } from "../components/ChatPanel";
import { ContentsPanel } from "../components/ContentsPanel";
import { JobStrip } from "../components/JobProgress";
import { SettingsPanel } from "../components/SettingsPanel";
import { SourcesDialog } from "../components/SourcesDialog";
import { TopicsPanel } from "../components/TopicsPanel";
import { Avatar, Button, Empty, Spinner, Tabs } from "../components/ui";

export type Tab = "contents" | "topics" | "config";

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
        { value: "config", label: "账号设定", icon: <Settings2 /> },
      ]}
    />
  );

  return (
    <div className="flex h-full flex-col bg-slate-50">
      <header className="z-30 shrink-0 border-b bg-card">
        <div className="flex items-center gap-3 px-3 sm:px-5">
          <Link to="/" title="所有账号" className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"><ArrowLeft className="size-4" /></Link>
          <div className="flex min-w-0 items-center gap-2 py-2.5">
            <Avatar name={account.name} size="sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold leading-tight">{account.name}</div>
              <div className="truncate text-xs text-muted-foreground">{account.theme || "定位还没定"}</div>
            </div>
          </div>
          <div className="ml-4 hidden self-end md:block">{tabs}</div>
          <Button variant="ghost" size="sm" className="ml-auto text-muted-foreground" onClick={() => setSourcesOpen(true)}><KeyRound />数据来源</Button>
        </div>
        <div className="overflow-x-auto px-2 md:hidden">{tabs}</div>
      </header>
      {sourcesOpen && <SourcesDialog onClose={() => setSourcesOpen(false)} />}

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto max-w-4xl px-4 py-5 sm:px-6">
            <JobStrip jobs={jobs} />
            {tab === "contents" && <ContentsPanel account={account} busy={writing} onGoTopics={() => setTab("topics")} />}
            {tab === "topics" && <TopicsPanel account={account} busy={writing} onGoConfig={() => setTab("config")} />}
            {tab === "config" && <SettingsPanel account={account} busy={writing} />}
          </div>
        </main>
        <aside className="hidden w-[380px] shrink-0 border-l lg:flex xl:w-[420px]">
          <ChatPanel account={account} />
        </aside>
      </div>

      {/* 窄屏：小媒收进右下角按钮 */}
      <button
        onClick={() => setChatOpen(true)}
        className="fixed bottom-5 right-5 z-40 flex cursor-pointer items-center gap-2 rounded-full bg-indigo-600 px-4 py-3 text-sm font-medium text-white shadow-xl shadow-indigo-600/30 lg:hidden"
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
