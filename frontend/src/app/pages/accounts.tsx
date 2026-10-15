import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Plus,
  Settings,
  Loader2,
  FileText,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  Sparkles,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface Account {
  id: string;
  username: string;
  nickname?: string;
  avatar_url?: string;
  theme?: string;
  target_audience?: string;
  status: string;
  draft_count: number;
  published_count: number;
  created_at: string;
}

export function AccountsPage() {
  const navigate = useNavigate();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newAccountName, setNewAccountName] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const getToken = () => localStorage.getItem("token");

  useEffect(() => {
    fetchAccounts();
  }, []);

  const fetchAccounts = async () => {
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAccounts(data.accounts || []);
      }
    } catch {}
    finally { setIsLoading(false); }
  };

  const handleCreateAccount = async () => {
    if (!newAccountName.trim()) return;
    setIsCreating(true);
    setCreateError("");
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ name: newAccountName.trim() }),
      });
      if (res.ok) {
        const data = await res.json();
        setShowCreateModal(false);
        setNewAccountName("");
        // 直接进入新账号工作台
        navigate(`/accounts/${data.id}`);
      } else {
        const err = await res.json().catch(() => ({}));
        setCreateError(err.detail || "创建失败，请重试");
      }
    } catch {
      setCreateError("网络错误，请重试");
    } finally {
      setIsCreating(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/auth");
  };

  const userName = (() => {
    try {
      const u = JSON.parse(localStorage.getItem("user") || "{}");
      return u.nickname || u.email?.split("@")[0] || "老板";
    } catch { return "老板"; }
  })();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-indigo-50 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950">
      {/* Header */}
      <header className="border-b bg-card/90 backdrop-blur-sm sticky top-0 z-50 shadow-sm">
        <div className="container mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-xl shadow-lg">
              🌀
            </div>
            <div>
              <div className="font-bold text-base bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
                媒力 MediaFlow
              </div>
              <div className="text-xs text-muted-foreground">账号孵化中台</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground hidden sm:block">
              Hi, {userName}
            </span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              退出
            </Button>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-6 py-10 max-w-5xl">
        {/* 页头 */}
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold mb-1">我的账号</h1>
            <p className="text-sm text-muted-foreground">
              每个账号是一条独立的内容赛道，点进去开始孵化
            </p>
          </div>
          <Button
            onClick={() => setShowCreateModal(true)}
            className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 shadow-lg"
          >
            <Plus className="w-4 h-4" />
            新建账号
          </Button>
        </div>

        {/* 账号列表 */}
        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
          </div>
        ) : accounts.length === 0 ? (
          <div className="text-center py-20">
            <div className="w-20 h-20 bg-indigo-100 dark:bg-indigo-900/30 rounded-2xl flex items-center justify-center text-4xl mx-auto mb-4">
              🌀
            </div>
            <h3 className="text-lg font-semibold mb-2">还没有账号</h3>
            <p className="text-muted-foreground text-sm mb-6">
              点击「新建账号」创建你的第一条运营赛道
            </p>
            <Button
              onClick={() => setShowCreateModal(true)}
              className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600"
            >
              <Plus className="w-4 h-4" />
              新建账号
            </Button>
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {accounts.map((acc) => (
              <Card
                key={acc.id}
                className="border-2 hover:border-indigo-300 dark:hover:border-indigo-700 hover:shadow-xl transition-all duration-300 cursor-pointer group"
                onClick={() => navigate(`/accounts/${acc.id}`)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 bg-gradient-to-br from-indigo-400 to-purple-500 rounded-xl flex items-center justify-center text-white font-bold text-lg flex-shrink-0">
                        {(acc.nickname || acc.username || "?")[0].toUpperCase()}
                      </div>
                      <div>
                        <CardTitle className="text-base leading-tight">
                          {acc.nickname || acc.username}
                        </CardTitle>
                        <div className="text-xs text-muted-foreground mt-0.5">
                          @{acc.username}
                        </div>
                      </div>
                    </div>
                    <Badge
                      variant="secondary"
                      className={`text-xs flex-shrink-0 ${
                        acc.status === "active"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {acc.status === "active" ? "运营中" : "未绑定"}
                    </Badge>
                  </div>

                  {/* 主题 */}
                  {acc.theme ? (
                    <div className="mt-3 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-indigo-500 flex-shrink-0" />
                      <CardDescription className="text-sm font-medium text-foreground">
                        {acc.theme}
                      </CardDescription>
                    </div>
                  ) : (
                    <div className="mt-3 flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
                      <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                      <span className="text-xs">主题未设定，进入工作台配置</span>
                    </div>
                  )}
                </CardHeader>

                <CardContent className="pt-0">
                  {/* 数据行 */}
                  <div className="flex items-center gap-4 text-sm text-muted-foreground border-t pt-3">
                    <div className="flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5" />
                      <span>{acc.draft_count} 篇草稿</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
                      <span>{acc.published_count} 篇已发</span>
                    </div>
                    <div className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity">
                      <ArrowRight className="w-4 h-4 text-indigo-500" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}

            {/* 新建占位卡 */}
            <Card
              className="border-2 border-dashed hover:border-indigo-400 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30 transition-all duration-300 cursor-pointer"
              onClick={() => setShowCreateModal(true)}
            >
              <CardContent className="flex flex-col items-center justify-center h-full min-h-[180px] text-muted-foreground gap-2">
                <div className="w-12 h-12 rounded-xl border-2 border-dashed flex items-center justify-center">
                  <Plus className="w-5 h-5" />
                </div>
                <span className="text-sm font-medium">新建账号</span>
              </CardContent>
            </Card>
          </div>
        )}
      </div>

      {/* 新建账号 Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={(e) => e.target === e.currentTarget && setShowCreateModal(false)}
        >
          <div className="bg-card rounded-2xl p-6 w-full max-w-md shadow-2xl">
            <h3 className="text-lg font-bold mb-1">新建账号</h3>
            <p className="text-sm text-muted-foreground mb-5">
              填写账号名称后，进入工作台与小媒对话来配置运营定位
            </p>

            {createError && (
              <div className="mb-4 flex items-center gap-2 p-3 bg-red-50 text-red-600 rounded-lg text-sm">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                {createError}
              </div>
            )}

            <div className="space-y-4">
              <div>
                <Label htmlFor="acc-name">账号名称（随便取，用于识别）</Label>
                <Input
                  id="acc-name"
                  value={newAccountName}
                  onChange={(e) => setNewAccountName(e.target.value)}
                  placeholder="如：精致下午茶、职场干货、母婴日记..."
                  className="mt-1"
                  onKeyDown={(e) => e.key === "Enter" && handleCreateAccount()}
                  autoFocus
                />
              </div>
              <div className="flex gap-3 pt-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => { setShowCreateModal(false); setCreateError(""); }}
                  disabled={isCreating}
                >
                  取消
                </Button>
                <Button
                  className="flex-1 bg-gradient-to-r from-indigo-500 to-purple-600"
                  onClick={handleCreateAccount}
                  disabled={isCreating || !newAccountName.trim()}
                >
                  {isCreating ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" />创建中...</>
                  ) : (
                    "创建并进入工作台"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
