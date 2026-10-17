import { AlertCircle } from "lucide-react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { useSystem } from "./api/hooks";
import { AccountsPage } from "./pages/AccountsPage";
import { DraftPage } from "./pages/DraftPage";
import { WorkspacePage } from "./pages/WorkspacePage";

/** 只有缺了必需的模型密钥才提示；可选项放在首页的「开始之前」清单里 */
function SystemBanner() {
  const { data } = useSystem();
  if (!data || data.llm_configured) return null;
  return (
    <div className="flex items-center justify-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-800">
      <AlertCircle className="size-3.5 shrink-0" />
      还没填 DeepSeek API Key，写稿和对话用不了。在 <code className="rounded bg-amber-100 px-1">server/.env</code> 里填 DEEPSEEK_API_KEY 后重启。
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
