import { ChevronLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { isActive, useAccount, useActiveJobs } from "../api/hooks";
import { ChatPanel } from "../components/ChatPanel";
import { DraftsPanel } from "../components/DraftsPanel";
import { JobProgress } from "../components/JobProgress";
import { ProfilePanel } from "../components/ProfilePanel";
import { TopicsPanel } from "../components/TopicsPanel";
import { Empty, ErrorText, Spinner, Tabs } from "../components/ui";

type Tab = "profile" | "topics" | "drafts";

export function WorkspacePage() {
  const { id = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "drafts";
  const { data: account, isLoading, error } = useAccount(id);
  const { data: jobs = [] } = useActiveJobs(id);
  const [hideDone, setHideDone] = useState<string[]>([]);

  if (isLoading) return <div className="p-8"><Spinner /></div>;
  if (!account) return <div className="p-8"><Empty title="找不到这个账号" /><ErrorText error={error} /></div>;

  const writing = jobs.some((j) => j.kind === "write_draft" && isActive(j));
  const visibleJobs = jobs.filter((j) => isActive(j) || !hideDone.includes(j.id)).slice(0, 3);

  return (
    <div className="flex h-full">
      <aside className="flex w-[380px] shrink-0 flex-col border-r border-line bg-white">
        <ChatPanel accountId={id} />
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-line bg-white px-4 py-3">
          <Link to="/" className="text-muted hover:text-ink" aria-label="返回"><ChevronLeft className="size-5" /></Link>
          <div className="font-semibold">{account.name}</div>
          {account.theme && <div className="truncate text-sm text-muted">· {account.theme}</div>}
        </div>
        <div className="bg-white">
          <Tabs<Tab>
            value={tab}
            onChange={(v) => setSp({ tab: v })}
            items={[{ value: "drafts", label: "草稿" }, { value: "topics", label: "选题" }, { value: "profile", label: "定位与规矩" }]}
          />
        </div>
        {visibleJobs.length > 0 && (
          <div className="space-y-2 border-b border-line bg-white px-4 py-3">
            {visibleJobs.map((j) => (
              <div key={j.id} className="relative">
                <JobProgress job={j} />
                {!isActive(j) && (
                  <button onClick={() => setHideDone([...hideDone, j.id])} className="absolute right-2 top-2 cursor-pointer text-xs text-muted hover:text-ink">关闭</button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="flex-1 overflow-y-auto">
          {tab === "profile" && <ProfilePanel account={account} />}
          {tab === "topics" && <TopicsPanel accountId={id} />}
          {tab === "drafts" && <DraftsPanel accountId={id} busy={writing} />}
        </div>
      </main>
    </div>
  );
}
