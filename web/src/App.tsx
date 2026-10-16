import { AlertCircle } from "lucide-react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { useSystem } from "./api/hooks";
import { AccountsPage } from "./pages/AccountsPage";
import { DraftPage } from "./pages/DraftPage";
import { WorkspacePage } from "./pages/WorkspacePage";

function SystemBanner() {
  const { data } = useSystem();
  if (!data) return null;
  const missing = [
    !data.llm_configured && "DEEPSEEK_API_KEY（写稿、对话都需要）",
    !data.image_configured && "配图服务密钥（不配也能用，只是没有图）",
  ].filter(Boolean);
  if (!missing.length) return null;
  return (
    <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
      <AlertCircle className="size-4 shrink-0" />
      <span>还没配置：{missing.join("；")}。在 <code>server/.env</code> 里填好后重启。</span>
    </div>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full flex-col">
        <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line bg-white px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <span className="flex size-7 items-center justify-center rounded-lg bg-brand text-sm text-white">媒</span>
            媒力 MediaFlow
          </Link>
          <span className="text-xs text-muted">小红书 AI 运营助手</span>
        </header>
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
