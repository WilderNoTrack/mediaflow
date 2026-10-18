import { ArrowLeft, Copy, FileText, Settings, TrendingUp } from "lucide-react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { isActive, useAccount, useActiveJobs } from "../api/hooks";
import { BenchmarkPanel } from "../components/BenchmarkPanel";
import { ConfigPanel } from "../components/ConfigPanel";
import { ContentsPanel } from "../components/ContentsPanel";
import { Header } from "../components/Header";
import { JobDock } from "../components/JobProgress";
import { TopicsPanel } from "../components/TopicsPanel";
import { Avatar, Button, Empty, Segmented, Spinner } from "../components/ui";

export type Tab = "contents" | "topics" | "bench" | "config";

export function WorkspacePage() {
  const { id = "" } = useParams();
  const [sp, setSp] = useSearchParams();
  const tab = (sp.get("tab") as Tab) || "contents";
  const setTab = (t: Tab) => setSp({ tab: t });
  const { data: account, isLoading } = useAccount(id);
  const { data: jobs = [] } = useActiveJobs(id);

  if (isLoading) return <div className="flex justify-center py-20"><Spinner className="size-6" /></div>;
  if (!account) return <Empty title="找不到这个账号" action={<Link to="/"><Button size="sm">回到账号列表</Button></Link>} />;

  const writing = jobs.some((j) => j.kind === "write_draft" && isActive(j));

  return (
    <div className="min-h-full bg-gradient-to-br from-slate-50 via-white to-indigo-50/40">
      <Header
        narrow
        left={<>
          <Link to="/"><Button variant="ghost" size="sm"><ArrowLeft />账号列表</Button></Link>
          <div className="flex min-w-0 items-center gap-2">
            <Avatar name={account.name} size="sm" />
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{account.name}</div>
              {account.theme && <div className="truncate text-xs text-muted-foreground">{account.theme}</div>}
            </div>
          </div>
        </>}
        right={
          <Segmented<Tab>
            value={tab}
            onChange={setTab}
            items={[
              { value: "contents", label: "内容", icon: <FileText /> },
              { value: "topics", label: "选题", icon: <TrendingUp /> },
              { value: "bench", label: "对标", icon: <Copy /> },
              { value: "config", label: "配置", icon: <Settings /> },
            ]}
          />
        }
      />
      <div className={`container mx-auto px-4 py-6 ${tab === "config" ? "max-w-5xl" : "max-w-4xl"}`}>
        {tab === "contents" && <ContentsPanel accountId={id} busy={writing} onGoTopics={() => setTab("topics")} />}
        {tab === "topics" && <TopicsPanel account={account} busy={writing} onGoConfig={() => setTab("config")} />}
        {tab === "bench" && <BenchmarkPanel account={account} jobs={jobs} onGoTopics={() => setTab("topics")} />}
        {tab === "config" && <ConfigPanel account={account} busy={writing} />}
      </div>
      <JobDock jobs={jobs} />
    </div>
  );
}
