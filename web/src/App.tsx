import { AlertCircle, Loader2 } from "lucide-react";
import { useState } from "react";
import { LlmKeyDialog } from "./components/LlmKeyDialog";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { useIsAdmin, useMe, useSystem } from "./api/hooks";
import { LoginPage } from "./pages/LoginPage";
import { AccountsPage } from "./pages/AccountsPage";
import { DraftPage } from "./pages/DraftPage";
import { WorkspacePage } from "./pages/WorkspacePage";

/** 只有缺了必需的模型密钥才提示；可选项放在首页的「开始之前」清单里 */
function SystemBanner() {
  const { data } = useSystem();
  const [open, setOpen] = useState(false);
  const admin = useIsAdmin();
  if (data && !data.llm_configured && !admin)
    return (
      <div className="flex items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-800">
        <AlertCircle className="size-3.5 shrink-0" />
        管理员还没配好模型，写稿和对话暂时用不了，请联系管理员。
      </div>
    );
  if (!data || (data.llm_configured && !open))
    return open ? <LlmKeyDialog onClose={() => setOpen(false)} /> : null;
  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-800">
      <AlertCircle className="size-3.5 shrink-0" />
      还没填 DeepSeek Key，写稿和对话用不了。
      <button
        className="cursor-pointer font-medium underline underline-offset-2"
        onClick={() => setOpen(true)}
      >
        现在去填
      </button>
      {open && <LlmKeyDialog onClose={() => setOpen(false)} />}
    </div>
  );
}

/** 在线版先登录；本地版 /api/auth/me 直接返回本机用户，不会看到登录页 */
function AuthGate({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading, error, refetch } = useMe();
  if (isLoading)
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="size-5 animate-spin" />
      </div>
    );
  if (error)
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
        连不上服务，稍后再试。
        <button className="cursor-pointer underline" onClick={() => refetch()}>
          重试
        </button>
      </div>
    );
  if (!me) return <LoginPage />;
  return <>{children}</>;
}

export function App() {
  return (
    <BrowserRouter>
      <AuthGate>
        <div className="flex h-full flex-col">
          <SystemBanner />
          <div className="min-h-0 flex-1 overflow-y-auto">
            <Routes>
              <Route path="/" element={<AccountsPage />} />
              <Route path="/accounts/:id" element={<WorkspacePage />} />
              <Route path="/drafts/:id" element={<DraftPage />} />
            </Routes>
          </div>
        </div>
      </AuthGate>
    </BrowserRouter>
  );
}
