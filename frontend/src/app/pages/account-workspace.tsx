import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate, useLocation, Link } from "react-router";
import { notifyJobStarted } from "@/components/GenerationProgress";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import {
  ArrowLeft, Search, Sparkles, Loader2, Send, FileText,
  CheckCircle2, Clock, ChevronDown, ChevronUp, Edit,
  Trash2, MessageCircle, Settings, Image as ImageIcon,
  RefreshCw, Save, AlertCircle, TrendingUp, Zap, Bot, Play, Wand2, X,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const resolveImg = (url: string) => url?.startsWith("/") ? `${API_BASE}${url}` : (url || "");

interface AgentEntry {
  type: string;
  tool?: string;
  args?: Record<string, any>;
  result?: Record<string, any>;
  score?: number;
  verdict?: string;
  issues?: string[];
  suggestions?: string[];
  message?: string;
  summary?: string;
  content_id?: string;
  title?: string;
  sub?: boolean;
  fallback?: boolean;
  fallback_reason?: string;
}

// 账号管家 + 内容创作 Agent 的工具展示元数据
const MANAGER_TOOL_META: Record<string, { icon: string; label: string }> = {
  get_account_profile:    { icon: "📋", label: "查看账号配置" },
  update_account_profile: { icon: "✏️", label: "更新账号配置" },
  list_recent_contents:   { icon: "🗂", label: "查看最近内容" },
  set_auto_operation:     { icon: "⏰", label: "设置自动运营" },
  create_post:            { icon: "🚀", label: "执行内容创作" },
  search_trending:        { icon: "🔍", label: "搜索热点选题" },
  get_account_history:    { icon: "📖", label: "查看账号历史" },
  generate_content:       { icon: "✍️", label: "生成图文内容" },
  evaluate_content:       { icon: "⭐", label: "评估内容质量" },
  save_draft:             { icon: "💾", label: "保存草稿" },
};

const PLATFORMS = [
  { id: "xiaohongshu", label: "小红书",   color: "bg-rose-100 text-rose-700" },
  { id: "bilibili",    label: "B站",      color: "bg-cyan-100 text-cyan-700" },
  { id: "douyin",      label: "抖音",     color: "bg-slate-100 text-slate-700" },
  { id: "weibo",       label: "微博",     color: "bg-orange-100 text-orange-700" },
  { id: "baidu",       label: "百度",     color: "bg-blue-100 text-blue-700" },
  { id: "weixin",      label: "微信文章", color: "bg-green-100 text-green-700" },
];

const HOT_SCORE_STARS = (score: string | number) => {
  const n = parseInt(String(score)) || 3;
  return "★".repeat(n) + "☆".repeat(Math.max(0, 5 - n));
};

type Tab = "topics" | "contents" | "config";

// ─── 选题类型展示（只读，来自小媒对话）────────────────────
function TopicTypeField({
  value, onGoConfig
}: { value: string; onGoConfig: () => void }) {
  return (
    <div className="mb-1">
      <span className="text-xs text-muted-foreground">选题类型</span>
      {value ? (
        <div className="mt-1 px-2.5 py-1.5 bg-indigo-50 dark:bg-indigo-900/20 rounded-lg text-xs text-indigo-700 dark:text-indigo-300 font-medium flex items-center justify-between">
          <span>{value}</span>
          <span className="text-indigo-400 font-normal opacity-60">来自配置</span>
        </div>
      ) : (
        <button
          onClick={onGoConfig}
          className="mt-1 w-full text-xs text-muted-foreground border border-dashed rounded-lg px-2.5 py-1.5 hover:border-indigo-300 hover:text-indigo-500 transition-colors text-left"
        >
          未设置 → 去「配置」Tab 和小媒对话确认
        </button>
      )}
    </div>
  );
}

// ─── 选题卡片 ─────────────────────────────────────────────
function TopicCard({
  topic,
  onSelect,
  onSkip,
  isGenerating,
}: {
  topic: any;
  onSelect: () => void;
  onSkip: () => void;
  isGenerating: boolean;
}) {
  const platform = PLATFORMS.find((p) => p.id === topic.source);
  return (
    <div className="border-2 rounded-xl p-4 hover:border-indigo-300 dark:hover:border-indigo-700 transition-all bg-card">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h4 className="font-medium text-sm leading-snug flex-1">{topic.title}</h4>
        {platform && (
          <Badge className={`text-xs flex-shrink-0 border-0 ${platform.color}`}>
            {platform.label}
          </Badge>
        )}
      </div>
      {topic.angle && (
        <p className="text-xs text-muted-foreground mb-3 leading-relaxed">{topic.angle}</p>
      )}
      <div className="flex items-center justify-between mt-2">
        <span className="text-xs text-amber-500 font-mono">{HOT_SCORE_STARS(topic.hot_score)}</span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-muted-foreground"
            onClick={onSkip}
          >
            跳过
          </Button>
          <Button
            size="sm"
            className="h-7 text-xs gap-1 bg-gradient-to-r from-indigo-500 to-purple-600"
            onClick={onSelect}
            disabled={isGenerating}
          >
            {isGenerating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
            生成图文
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── 内容卡片 ─────────────────────────────────────────────
function ContentCard({ item, onEdit, onPreview }: { item: any; onEdit: () => void; onPreview: () => void }) {
  const statusMap: Record<string, { label: string; cls: string }> = {
    draft: { label: "草稿", cls: "bg-gray-100 text-gray-600" },
    published: { label: "已发布", cls: "bg-green-100 text-green-700" },
    pending: { label: "待发布", cls: "bg-blue-100 text-blue-700" },
    failed: { label: "失败", cls: "bg-red-100 text-red-700" },
  };
  const s = statusMap[item.status] || { label: item.status, cls: "bg-gray-100 text-gray-600" };

  return (
    <div
      className="border rounded-xl p-4 bg-card hover:shadow-md hover:border-indigo-300 dark:hover:border-indigo-700 transition-all cursor-pointer"
      onClick={onPreview}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h4 className="font-medium text-sm leading-snug flex-1 line-clamp-2">{item.title || "无标题"}</h4>
        <Badge className={`text-xs border-0 flex-shrink-0 ${s.cls}`}>{s.label}</Badge>
      </div>

      {/* 质检与配图状态：以前这些信息只落在库里/日志里，界面上看不见 */}
      {(item.needs_review || item.quality_score || (item.image_status && item.image_status !== "none" && item.image_status !== "done")) && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2">
          {item.needs_review && (
            <Badge className="text-[10px] border-0 bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-400">
              ⚠ 未经质检
            </Badge>
          )}
          {item.quality_score && !item.needs_review && (
            <Badge className="text-[10px] border-0 bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400">
              质检 {item.quality_score}/10
            </Badge>
          )}
          {item.image_status === "pending" && (
            <Badge className="text-[10px] border-0 bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400">
              配图生成中…
            </Badge>
          )}
          {item.image_status === "partial" && (
            <Badge className="text-[10px] border-0 bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400">
              部分配图失败
            </Badge>
          )}
          {item.image_status === "failed" && (
            <Badge className="text-[10px] border-0 bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-400">
              配图失败
            </Badge>
          )}
        </div>
      )}

      {item.images && item.images.length > 0 && (
        <div className="flex gap-1.5 mb-3">
          {item.images.slice(0, 3).map((img: string, i: number) => (
            <div key={i} className="w-14 h-[75px] rounded-lg overflow-hidden flex-shrink-0 bg-muted">
              <img src={resolveImg(img)} alt="" className="w-full h-full object-cover" />
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground leading-relaxed mb-2 line-clamp-3">
        {item.content || ""}
      </p>

      {item.tags && item.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {item.tags.slice(0, 4).map((tag: string, i: number) => (
            <span key={i} className="text-xs text-indigo-600 dark:text-indigo-400">#{tag}</span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between border-t pt-2">
        <span className="text-xs text-muted-foreground">
          {new Date(item.created_at).toLocaleDateString("zh-CN")}
        </span>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs gap-1"
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
        >
          <Edit className="w-3 h-3" />编辑
        </Button>
      </div>
    </div>
  );
}

// ─── 主页面 ───────────────────────────────────────────────
export function AccountWorkspacePage() {
  const { accountId } = useParams<{ accountId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [tab, setTab] = useState<Tab>("contents");

  const [profile, setProfile] = useState<any>(null);
  const [isLoadingProfile, setIsLoadingProfile] = useState(true);

  // 选题 tab
  const [keyword, setKeyword] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState(["xiaohongshu", "bilibili", "douyin", "weibo", "baidu", "weixin"]);
  const [topics, setTopics] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [platformStatus, setPlatformStatus] = useState<Record<string, 'idle'|'loading'|'done'|'error'>>({});
  const [platformCounts, setPlatformCounts] = useState<Record<string, number>>({});
  const [platformItems, setPlatformItems] = useState<Record<string, Array<{title:string,hot_value:string,url:string,note_id?:string,xsec_token?:string,bvid?:string,author?:string,cover?:string,snippet?:string}>>>({});
  const [detailPanel, setDetailPanel] = useState<{platform:string,item:any}|null>(null);
  const [detailData, setDetailData] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [platformAiGenerated, setPlatformAiGenerated] = useState<Record<string, boolean>>({});
  const [showRawResults, setShowRawResults] = useState(false);
  const [generatingTopicId, setGeneratingTopicId] = useState<string | null>(null);
  const [generatedContent, setGeneratedContent] = useState<any | null>(null);
  const [suggestedKeywords, setSuggestedKeywords] = useState<string[]>([]);
  const [seenKeywords, setSeenKeywords] = useState<Set<string>>(new Set());
  const [isSuggestingKw, setIsSuggestingKw] = useState(false);
  const [suggestKwError, setSuggestKwError] = useState("");

  // 关键词编辑
  const [editingKeywords, setEditingKeywords] = useState<string[]>([]);
  const [isEditingKw, setIsEditingKw] = useState(false);
  const [isSavingKw, setIsSavingKw] = useState(false);

  // 内容 tab
  const [contents, setContents] = useState<any[]>([]);
  const [isLoadingContents, setIsLoadingContents] = useState(false);
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeletingBatch, setIsDeletingBatch] = useState(false);

  // 配置 tab
  const [chatMessages, setChatMessages] = useState<{ role: string; message: string; options?: string[]; activity?: AgentEntry[] }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatting, setIsChatting] = useState(false);
  const [chatActivity, setChatActivity] = useState<AgentEntry[]>([]);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [configSaved, setConfigSaved] = useState(false);
  const [profileForm, setProfileForm] = useState({
    theme: "", target_audience: "", content_style: "", image_style: "",
    topic_type: "", keywords: "", requirements: ""
  });
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 生成进度 overlay
  const [generationProgress, setGenerationProgress] = useState<{
    topicTitle: string;
    steps: { label: string; status: 'pending' | 'running' | 'done' | 'error' }[];
    generatedTitle?: string;
    previewTitle?: string;
    previewContent?: string;
    expandedPrompts?: { index: number; prompt: string }[];
    warnings?: string[];
    done?: boolean;
  } | null>(null);

  const [agentLog,     setAgentLog]     = useState<AgentEntry[]>([]);
  const [agentDone,    setAgentDone]    = useState<{success: boolean; content_id?: string; title?: string; error?: string} | null>(null);

  // 自动运营
  const [autoConfig, setAutoConfig] = useState({
    auto_enabled: false,
    auto_frequency: "daily",
    auto_count: 1,
    last_auto_run: null as string | null,
    next_run: null as string | null,
  });
  const [isRunningNow, setIsRunningNow] = useState(false);
  const [autoRunResult, setAutoRunResult] = useState<any>(null);

  const getToken = () => localStorage.getItem("token");
  const headers = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken()}`,
  });

  useEffect(() => { fetchProfile(); fetchAutoConfig(); }, [accountId]);
  useEffect(() => { if (tab === "contents") fetchContents(); }, [tab, location.key]);
  useEffect(() => { if (tab === "config") { fetchChatHistory(); fetchAutoConfig(); } }, [tab]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages, chatActivity]);

  const fetchAutoConfig = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/auto`, { headers: headers() });
      if (res.ok) setAutoConfig(await res.json());
    } catch {}
  };

  const handleToggleAuto = async (enabled: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/auto`, {
        method: "PUT", headers: headers(),
        body: JSON.stringify({ ...autoConfig, auto_enabled: enabled }),
      });
      if (res.ok) setAutoConfig(await res.json());
      else { const e = await res.json(); alert(e.detail || "设置失败"); }
    } catch { alert("网络错误"); }
  };

  const handleSaveAutoFrequency = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/auto`, {
        method: "PUT", headers: headers(),
        body: JSON.stringify(autoConfig),
      });
      if (res.ok) setAutoConfig(await res.json());
    } catch {}
  };

  const handleRunNow = async () => {
    setIsRunningNow(true);
    setAutoRunResult(null);
    setAgentLog([]);
    setAgentDone(null);
    // 让顶部全局进度条立刻感知，不用等它下一轮轮询
    notifyJobStarted();

    try {
      const res = await fetch(`${API_BASE}/api/agent/run/${accountId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok || !res.body) {
        const e = await res.json().catch(() => ({}));
        setAgentDone({ success: false, error: e.detail || "启动失败" });
        setIsRunningNow(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let ev: AgentEntry;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }

          setAgentLog((prev) => [...prev, ev]);

          if (ev.type === "done") {
            setAgentDone({ success: true, content_id: ev.content_id, title: ev.title });
            fetchContents();
            fetchAutoConfig();
          }
          if (ev.type === "error") {
            setAgentDone({ success: false, error: ev.message });
          }
        }
      }
    } catch (e: any) {
      setAgentDone({ success: false, error: e?.message || "网络错误" });
    }

    setIsRunningNow(false);
  };

  const fetchProfile = async () => {
    setIsLoadingProfile(true);
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/profile`, {
        headers: headers(),
      });
      if (res.ok) {
        const data = await res.json();
        setProfile(data);
        setProfileForm({
          theme: data.theme || "",
          target_audience: data.target_audience || "",
          content_style: data.content_style || "",
          image_style: data.image_style || "",
          topic_type: data.topic_type || "",
          keywords: (data.keywords || []).join(", "),
          requirements: (data.requirements || []).join("\n"),
        });
      }
    } catch {}
    finally { setIsLoadingProfile(false); }
  };

  const fetchContents = async () => {
    setIsLoadingContents(true);
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/contents`, {
        headers: headers(),
      });
      if (res.ok) setContents((await res.json()).contents || []);
    } catch {}
    finally { setIsLoadingContents(false); }
  };

  const fetchChatHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/chat-history`, {
        headers: headers(),
      });
      if (res.ok) {
        const data = await res.json();
        setChatMessages(data.history || []);
        if ((data.history || []).length === 0) {
          setChatMessages([{
            role: "assistant",
            message: `你好！我是小媒 🌀 「${profile?.username || "这个账号"}」的账号管家。\n\n直接跟我聊就行——比如「我想做一个美式街头穿搭账号」，我会边聊边帮你把定位配置好；配置差不多了说一句「发一篇试试」，我就直接帮你创作。\n\n这个账号想做什么方向？`,
          }]);
        }
      }
    } catch {}
  };

  // ─── 关键词编辑 & 保存 ────────────────────────────────
  const startEditKeywords = () => {
    setEditingKeywords([...(profile?.keywords || []), ""]);
    setIsEditingKw(true);
  };

  const saveKeywords = async () => {
    const clean = editingKeywords.map(k => k.trim()).filter(Boolean);
    setIsSavingKw(true);
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/profile`, {
        method: "PUT", headers: headers(),
        body: JSON.stringify({ keywords: clean }),
      });
      if (res.ok) {
        await fetchProfile();
        setIsEditingKw(false);
      }
    } catch {} finally { setIsSavingKw(false); }
  };

  // ─── 批量删除 ──────────────────────────────────────────
  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const enterSelectMode = () => { setIsSelectMode(true); setSelectedIds(new Set()); };
  const exitSelectMode = () => { setIsSelectMode(false); setSelectedIds(new Set()); };

  const handleBatchDelete = async () => {
    if (!selectedIds.size) return;
    if (!confirm(`确定删除选中的 ${selectedIds.size} 篇内容？此操作不可撤销。`)) return;
    setIsDeletingBatch(true);
    try {
      await Promise.all([...selectedIds].map(id =>
        fetch(`${API_BASE}/api/contents/${id}`, { method: "DELETE", headers: headers() })
      ));
      exitSelectMode();
      fetchContents();
    } catch {} finally { setIsDeletingBatch(false); }
  };

  // ─── AI 推荐关键词 ─────────────────────────────────────
  const handleSuggestKeywords = async () => {
    setIsSuggestingKw(true);
    setSuggestKwError("");
    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/suggest-keywords`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ exclude: Array.from(seenKeywords) }),
      });
      if (res.ok) {
        const data = await res.json();
        const fresh = (data.keywords || []).filter((k: string) => !seenKeywords.has(k));
        setSuggestedKeywords(fresh);
        setSeenKeywords(prev => new Set([...prev, ...fresh]));
        // 自动打开关键词编辑模式，合并新词，让用户确认后保存
        if (fresh.length > 0) {
          const existing = (profile?.keywords || []) as string[];
          const merged = [...new Set([...existing, ...fresh])];
          setEditingKeywords([...merged, ""]);
          setIsEditingKw(true);
        }
      } else {
        setSuggestKwError(`请求失败 (${res.status})，请重启后端`);
      }
    } catch {
      setSuggestKwError("网络错误，请检查后端是否运行");
    } finally {
      setIsSuggestingKw(false);
    }
  };

  // ─── 平台结果详情 ──────────────────────────────────────
  const openDetail = async (platform: string, item: any) => {
    setDetailPanel({ platform, item });
    setDetailData(null);

    if (platform === "bilibili") {
      const bvid = item.bvid || item.url?.split("/video/")[1]?.split("?")[0] || "";
      if (!bvid) { setDetailData({ error: "无法获取 BV 号" }); return; }
      setDetailLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/workspace/bilibili-video-detail?bvid=${bvid}`, { headers: headers() });
        setDetailData(await res.json());
      } catch { setDetailData({ error: "获取失败" }); }
      finally { setDetailLoading(false); }
      return;
    }

    if (platform === "xiaohongshu") {
      const noteId = item.note_id || item.url?.split("/explore/")[1]?.split("?")[0]?.split("#")[0] || "";
      if (!noteId) { setDetailData({ error: "无法获取笔记 ID" }); return; }
      setDetailLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/workspace/xhs-note-detail`, {
          method: "POST",
          headers: headers(),
          body: JSON.stringify({ note_id: noteId, xsec_token: item.xsec_token || "" }),
        });
        setDetailData(await res.json());
      } catch { setDetailData({ error: "获取失败" }); }
      finally { setDetailLoading(false); }
      return;
    }

    if (platform === "weixin") {
      // Snippet extracted during search — show immediately
      if (item.snippet || item.author) {
        setDetailData({ snippet: item.snippet || "", account: item.author || "", url: item.url || "" });
        // Also try to fetch full article if it's a direct mp.weixin.qq.com link
        const url = item.url || "";
        if (url.includes("mp.weixin.qq.com")) {
          setDetailLoading(true);
          try {
            const res = await fetch(`${API_BASE}/api/workspace/weixin-article-detail?url=${encodeURIComponent(url)}`, { headers: headers() });
            const d = await res.json();
            if (!d.sogou_blocked && !d.error) {
              setDetailData(prev => ({ ...prev, ...d }));
            }
          } catch {}
          finally { setDetailLoading(false); }
        }
        return;
      }
      // No snippet — try backend for direct links only
      const url = item.url || "";
      if (!url) { setDetailData({ snippet: "", url: "" }); return; }
      if (url.includes("mp.weixin.qq.com")) {
        setDetailLoading(true);
        try {
          const res = await fetch(`${API_BASE}/api/workspace/weixin-article-detail?url=${encodeURIComponent(url)}`, { headers: headers() });
          setDetailData(await res.json());
        } catch { setDetailData({ snippet: "", url }); }
        finally { setDetailLoading(false); }
      } else {
        setDetailData({ snippet: "", url });
      }
      return;
    }

    if (platform === "weibo") {
      // Hot search items — show available data immediately, no fetch
      setDetailData({ hot_value: item.hot_value || "", url: item.url || "", needs_login: true });
      return;
    }

    if (platform === "baidu") {
      // Show snippet immediately if available
      if (item.snippet) {
        setDetailData({ snippet: item.snippet, url: item.url });
        return;
      }
      const url = item.url || "";
      // AI-generated results have no real URL
      if (!url || url.includes("baidu.com/s?wd=") || !url.startsWith("http")) {
        setDetailData({ snippet: "", url, ai_item: true });
        return;
      }
      setDetailLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/workspace/baidu-link-detail?url=${encodeURIComponent(url)}`, { headers: headers() });
        const d = await res.json();
        setDetailData(d.fetch_failed ? { snippet: "", url, fetch_failed: true } : d);
      } catch { setDetailData({ snippet: "", url, fetch_failed: true }); }
      finally { setDetailLoading(false); }
      return;
    }
  };

  // ─── 选题流式搜索 ──────────────────────────────────────
  const handleSearch = async () => {
    if (!keyword.trim()) return;
    setIsSearching(true);
    setGeneratedContent(null);
    setTopics([]);
    // 初始化平台状态
    const initStatus: Record<string, 'idle'|'loading'|'done'|'error'> = {};
    selectedPlatforms.forEach(p => { initStatus[p] = 'idle'; });
    setPlatformStatus(initStatus);
    setPlatformCounts({});
    setPlatformItems({});
    setShowRawResults(true);

    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/search-topics-stream`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ keyword: keyword.trim(), platforms: selectedPlatforms }),
      });
      if (!res.body) throw new Error("no stream");

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const msg = JSON.parse(line.slice(6));
            if (msg.type === "platform_start") {
              setPlatformStatus(prev => ({ ...prev, [msg.platform]: "loading" }));
            } else if (msg.type === "platform_done") {
              setPlatformStatus(prev => ({ ...prev, [msg.platform]: "done" }));
              setPlatformCounts(prev => ({ ...prev, [msg.platform]: msg.count }));
              setPlatformAiGenerated(prev => ({ ...prev, [msg.platform]: !!msg.ai_generated }));
              if (msg.items?.length) {
                setPlatformItems(prev => ({ ...prev, [msg.platform]: msg.items }));
              }
            } else if (msg.type === "platform_error") {
              setPlatformStatus(prev => ({ ...prev, [msg.platform]: "error" }));
            } else if (msg.type === "complete") {
              setTopics(msg.topics || []);
            }
          } catch {}
        }
      }
    } catch (e) {
      console.error("search error", e);
    } finally {
      setIsSearching(false);
      setPlatformStatus({});
    }
  };

  const handleGenerateFromTopic = async (topicId: string) => {
    const topic = topics.find((t) => t.id === topicId);
    if (!topic) return;

    setGeneratingTopicId(topicId);
    setGeneratedContent(null);

    const STEPS = [
      { label: "分析选题角度", status: 'running' as const },
      { label: "AI 生成标题和正文（约40秒）", status: 'pending' as const },
      { label: "规划配图，扩写提示词", status: 'pending' as const },
      { label: "保存草稿", status: 'pending' as const },
    ];
    setGenerationProgress({ topicTitle: topic.title, steps: STEPS });

    const upd = (updater: (prev: typeof STEPS) => typeof STEPS) =>
      setGenerationProgress((prev) => prev ? { ...prev, steps: updater(prev.steps) } : null);

    const setStepStatus = (idx: number, status: 'pending' | 'running' | 'done' | 'error') =>
      upd((steps) => steps.map((s, i) => i === idx ? { ...s, status } : s));

    try {
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/generate`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ topic_id: topicId }),
      });

      if (!res.ok || !res.body) {
        const errBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        setGenerationProgress((prev) => prev ? {
          ...prev,
          steps: prev.steps.map((s, i) => i === 1 ? { ...s, status: 'error' } : s),
          generatedTitle: `失败：${errBody.detail || res.status}`,
          done: true,
        } : null);
        setGeneratingTopicId(null);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let finalData: any = null;

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let ev: any;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }

          if (ev.type === "step") {
            setStepStatus(ev.index, ev.status);
          } else if (ev.type === "content") {
            // 文案到了：step1 完成，step2 开始，显示预览
            setGenerationProgress((prev) => prev ? {
              ...prev,
              steps: prev.steps.map((s, i) =>
                i === 1 ? { ...s, status: 'done' }
                : i === 2 ? { ...s, status: 'running' }
                : s),
              previewTitle: ev.data?.title || "",
              previewContent: ev.data?.content || "",
            } : null);
          } else if (ev.type === "prompt_expanded") {
            setGenerationProgress((prev) => prev ? {
              ...prev,
              expandedPrompts: [...(prev.expandedPrompts || []), { index: ev.index, prompt: ev.prompt }],
            } : null);
          } else if (ev.type === "warning") {
            setGenerationProgress((prev) => prev ? {
              ...prev,
              warnings: [...(prev.warnings || []), ev.message],
            } : null);
          } else if (ev.type === "error") {
            setGenerationProgress((prev) => prev ? {
              ...prev,
              steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'error' } : s),
              generatedTitle: `失败：${ev.message}`,
              done: true,
            } : null);
            setGeneratingTopicId(null);
            break outer;
          } else if (ev.type === "done") {
            finalData = ev;
            setGenerationProgress((prev) => prev ? {
              ...prev,
              steps: prev.steps.map((s) => ({ ...s, status: 'done' })),
              generatedTitle: ev.title,
              done: true,
            } : null);
            break outer;
          }
        }
      }

      if (finalData) {
        setGeneratedContent(finalData);
        setTopics((prev) => prev.map((t) => t.id === topicId ? { ...t, status: "used" } : t));
      }
    } catch (e: any) {
      setGenerationProgress((prev) => prev ? {
        ...prev,
        steps: prev.steps.map((s) => s.status === 'running' ? { ...s, status: 'error' } : s),
        generatedTitle: `失败：${e?.message || "网络错误"}`,
        done: true,
      } : null);
    }

    setGeneratingTopicId(null);
  };

  const handleSkipTopic = async (topicId: string) => {
    try {
      await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/topics/${topicId}/status`, {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify({ status: "skipped" }),
      });
      setTopics((prev) => prev.filter((t) => t.id !== topicId));
    } catch {}
  };

  // ─── 账号管家对话（ReAct Agent，SSE 流式）──────────────
  const sendChatMessage = async (msg: string) => {
    if (!msg.trim() || isChatting) return;
    setChatMessages((prev) => [...prev, { role: "user", message: msg }]);
    setIsChatting(true);
    setChatActivity([]);
    let activity: AgentEntry[] = [];
    let gotReply = false;
    try {
      const res = await fetch(`${API_BASE}/api/agent/chat/${accountId}`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ message: msg }),
      });
      if (!res.ok || !res.body) throw new Error("请求失败");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let e: any;
          try { e = JSON.parse(line.slice(6)); } catch { continue; }

          if (e.type === "tool_call") {
            activity = [...activity, e];
            setChatActivity(activity);
          } else if (e.type === "agent_progress" && e.event) {
            // create_post 子 Agent 的进度事件（嵌套展示）
            const inner = e.event;
            if (inner.type === "tool_call" || inner.type === "evaluation" || inner.type === "done" || inner.type === "warning") {
              activity = [...activity, { ...inner, sub: true }];
              setChatActivity(activity);
              if (inner.type === "done") fetchContents();
            }
          } else if (e.type === "profile_updated") {
            fetchProfile();
            fetchAutoConfig();
          } else if (e.type === "assistant_message") {
            gotReply = true;
            const acts = activity;
            setChatMessages((prev) => [...prev, {
              role: "assistant",
              message: e.content,
              activity: acts.length ? acts : undefined,
            }]);
          } else if (e.type === "error") {
            gotReply = true;
            setChatMessages((prev) => [...prev, { role: "assistant", message: `⚠️ 出错了：${e.message}` }]);
          }
        }
      }
      if (!gotReply) {
        setChatMessages((prev) => [...prev, { role: "assistant", message: "⚠️ 连接中断了，请再发一次" }]);
      }
    } catch {
      if (!gotReply) {
        setChatMessages((prev) => [...prev, { role: "assistant", message: "⚠️ 网络错误，请稍后再试" }]);
      }
    }
    finally { setIsChatting(false); setChatActivity([]); }
  };

  const handleChat = async () => {
    if (!chatInput.trim() || isChatting) return;
    const msg = chatInput.trim();
    setChatInput("");
    await sendChatMessage(msg);
  };

  const handleChatWithMessage = async (msg: string) => {
    if (isChatting) return;
    setChatInput("");
    await sendChatMessage(msg);
  };

  // 聊天流中的 Agent 工具活动（小字行，create_post 子流程缩进）
  const renderChatActivity = (entries: AgentEntry[], live: boolean) => (
    <div className="ml-9 mb-1.5 space-y-0.5">
      {entries.map((a, j) => {
        if (a.type === "warning") return (
          <p key={j} className={`text-xs text-amber-600 ${a.sub ? "pl-4" : ""}`}>
            ⚠️ {a.message}
          </p>
        );
        if (a.type === "evaluation") return (
          <p key={j} className="text-xs text-muted-foreground pl-4">
            {a.fallback ? "⚠️ 评估失败 · 未真实评估，默认放行" : `⭐ 质量评分 ${a.score}/10 · ${a.verdict}`}
          </p>
        );
        if (a.type === "done") return (
          <p key={j} className="text-xs text-green-600 pl-4">
            ✅ 草稿已保存{a.title ? `：「${a.title}」` : ""}
          </p>
        );
        const meta = MANAGER_TOOL_META[a.tool ?? ""] ?? { icon: "🔧", label: a.tool ?? "" };
        return (
          <p key={j} className={`text-xs text-muted-foreground flex items-center gap-1.5 ${a.sub ? "pl-4" : ""}`}>
            <span>{meta.icon}</span>
            <span>{meta.label}</span>
            {live && j === entries.length - 1 && (
              <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
            )}
          </p>
        );
      })}
    </div>
  );

  const handleSaveConfig = async () => {
    setIsSavingConfig(true);
    try {
      const extractRes = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/extract-config`, {
        method: "POST",
        headers: headers(),
      });
      if (extractRes.ok) {
        const data = await extractRes.json();
        const saved = data.saved || {};
        // 直接把提取结果同步到表单，不需要再 fetchProfile
        setProfileForm({
          theme: saved.theme || "",
          target_audience: saved.target_audience || "",
          content_style: saved.content_style || "",
          image_style: saved.image_style || "",
          topic_type: saved.topic_type || "",
          keywords: (saved.keywords || []).join(", "),
          requirements: (saved.requirements || []).join("\n"),
        });
        await fetchProfile();
        setConfigSaved(true);
        setTimeout(() => setConfigSaved(false), 4000);
      }
    } catch {}
    finally { setIsSavingConfig(false); }
  };

  const handleSaveProfileForm = async () => {
    setIsSavingConfig(true);
    try {
      const keywords = profileForm.keywords.split(",").map(k => k.trim()).filter(Boolean);
      const requirements = profileForm.requirements.split("\n").map(r => r.trim()).filter(Boolean);
      const res = await fetch(`${API_BASE}/api/workspace/accounts/${accountId}/profile`, {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify({
          theme: profileForm.theme || null,
          target_audience: profileForm.target_audience || null,
          content_style: profileForm.content_style || null,
          image_style: profileForm.image_style || null,
          topic_type: profileForm.topic_type || null,
          keywords,
          requirements,
        }),
      });
      if (res.ok) {
        await fetchProfile();
        setConfigSaved(true);
        setTimeout(() => setConfigSaved(false), 3000);
      }
    } catch {}
    finally { setIsSavingConfig(false); }
  };

  if (isLoadingProfile) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  const StepRow = ({ label, status }: { label: string; status: 'pending' | 'running' | 'done' | 'error' }) => (
    <div className="flex items-center gap-3 py-2">
      <div className="w-5 h-5 flex items-center justify-center flex-shrink-0">
        {status === 'done' && <CheckCircle2 className="w-5 h-5 text-green-500" />}
        {status === 'running' && <Loader2 className="w-5 h-5 text-indigo-500 animate-spin" />}
        {status === 'error' && <AlertCircle className="w-5 h-5 text-red-500" />}
        {status === 'pending' && <div className="w-4 h-4 rounded-full border-2 border-gray-300" />}
      </div>
      <span className={`text-sm ${status === 'done' ? 'text-green-700' : status === 'running' ? 'text-indigo-700 font-medium' : status === 'error' ? 'text-red-700' : 'text-muted-foreground'}`}>
        {label}
      </span>
      <span className="ml-auto text-xs text-muted-foreground">
        {status === 'done' ? '完成' : status === 'running' ? '进行中...' : status === 'error' ? '失败' : '等待中'}
      </span>
    </div>
  );

  return (
    <div className="min-h-screen bg-background">
      {/* Generation Progress Overlay */}
      {generationProgress && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl p-6 w-full max-w-md">
            <h3 className="font-semibold text-base mb-1">正在生成图文...</h3>
            <p className="text-xs text-muted-foreground mb-4 line-clamp-1">{generationProgress.topicTitle}</p>
            <div className="divide-y">
              {generationProgress.steps.map((step, i) => (
                <StepRow key={i} label={step.label} status={step.status} />
              ))}
            </div>

            {/* 文案预览（文案生成完立即显示） */}
            {generationProgress.previewTitle && !generationProgress.done && (
              <div className="mt-3 p-3 rounded-lg bg-indigo-50 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <p className="text-xs font-medium text-indigo-700 dark:text-indigo-300 line-clamp-1 mb-1">
                  《{generationProgress.previewTitle}》
                </p>
                <p className="text-xs text-muted-foreground line-clamp-2">{generationProgress.previewContent}</p>
              </div>
            )}

            {/* 提示词扩写进度（实时逐条出现） */}
            {(generationProgress.expandedPrompts?.length ?? 0) > 0 && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-muted-foreground mb-1">配图提示词：</p>
                {generationProgress.expandedPrompts!.map((ep) => (
                  <div key={ep.index}
                    className="text-xs px-2 py-1.5 rounded bg-gray-50 dark:bg-gray-800 text-muted-foreground line-clamp-1 animate-in fade-in slide-in-from-left-2 duration-200">
                    <span className="font-medium text-indigo-600 dark:text-indigo-400 mr-1">图{ep.index + 1}</span>
                    {ep.prompt}
                  </div>
                ))}
              </div>
            )}

            {/* 兜底/降级警告 */}
            {(generationProgress.warnings?.length ?? 0) > 0 && (
              <div className="mt-3 space-y-1">
                {generationProgress.warnings!.map((w, i) => (
                  <p key={i} className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded px-2 py-1.5">
                    ⚠️ {w}
                  </p>
                ))}
              </div>
            )}

            {generationProgress.done && (
              <div className="mt-4 pt-4 border-t">
                <p className="text-sm font-medium text-green-600 flex items-center gap-2 mb-3">
                  <CheckCircle2 className="w-4 h-4" />
                  生成完成！
                </p>
                {generationProgress.generatedTitle && (
                  <p className="text-xs text-muted-foreground mb-3 line-clamp-2">《{generationProgress.generatedTitle}》</p>
                )}
                <Button
                  size="sm"
                  className="w-full gap-2 bg-green-600 hover:bg-green-700"
                  onClick={() => { setGenerationProgress(null); setTab("contents"); fetchContents(); }}
                >
                  <FileText className="w-3.5 h-3.5" />查看内容
                </Button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Agent Run Overlay */}
      {(isRunningNow || agentDone) && (agentLog.length > 0 || agentDone) && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-md flex flex-col" style={{ maxHeight: "80vh" }}>
            {/* Header */}
            <div className="px-5 pt-5 pb-3 border-b flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-2">
                {isRunningNow
                  ? <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                  : agentDone?.success
                    ? <CheckCircle2 className="w-4 h-4 text-green-500" />
                    : <AlertCircle className="w-4 h-4 text-red-500" />
                }
                <span className="font-semibold text-sm">
                  {isRunningNow ? "Agent 运行中…" : agentDone?.success ? "内容创作完成" : "运行出错"}
                </span>
              </div>
              {agentDone && (
                <button
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => { setAgentLog([]); setAgentDone(null); }}
                >关闭</button>
              )}
            </div>

            {/* Log scroll area */}
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 text-sm">
              {agentLog.map((entry, i) => {
                if (entry.type === "start") return (
                  <p key={i} className="text-xs text-muted-foreground">{entry.summary}</p>
                );
                if (entry.type === "warning") return (
                  <p key={i} className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-1.5">
                    ⚠️ {entry.message}
                  </p>
                );
                if (entry.type === "tool_call") {
                  const icons: Record<string, string> = {
                    search_trending:    "🔍",
                    get_account_history:"📋",
                    generate_content:   "✍️",
                    evaluate_content:   "⭐",
                    save_draft:         "💾",
                  };
                  const labels: Record<string, string> = {
                    search_trending:    "搜索热点选题",
                    get_account_history:"查看账号历史",
                    generate_content:   "生成图文内容",
                    evaluate_content:   "评估内容质量",
                    save_draft:         "保存草稿",
                  };
                  return (
                    <div key={i} className="flex items-center gap-2 py-0.5">
                      <span className="text-base w-5 text-center">{icons[entry.tool ?? ""] ?? "🔧"}</span>
                      <span className="font-medium text-gray-800 dark:text-gray-200">
                        {labels[entry.tool ?? ""] ?? entry.tool}
                      </span>
                      {i === agentLog.length - 1 && isRunningNow && (
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400 ml-auto" />
                      )}
                    </div>
                  );
                }
                if (entry.type === "tool_result" && entry.result) {
                  const r = entry.result as any;
                  if (entry.tool === "search_trending" && r.top_topics?.length) return (
                    <p key={i} className="text-xs text-muted-foreground pl-7">
                      {r.summary} · 推荐：{r.top_topics.slice(0, 2).join("、")}
                    </p>
                  );
                  if (entry.tool === "get_account_history") return (
                    <p key={i} className="text-xs text-muted-foreground pl-7">{r.summary}</p>
                  );
                  if (entry.tool === "generate_content" && r.title) return (
                    <div key={i} className="pl-7 space-y-0.5">
                      <p className="text-xs font-medium text-gray-700 dark:text-gray-300">「{r.title}」</p>
                      <p className="text-xs text-muted-foreground line-clamp-2">{r.preview}</p>
                      <p className="text-xs text-muted-foreground">配图方案 {r.image_count} 张</p>
                    </div>
                  );
                  if (entry.tool === "save_draft") return (
                    <p key={i} className="text-xs text-green-600 pl-7">{r.message}</p>
                  );
                  return null;
                }
                if (entry.type === "evaluation") return (
                  <div key={i} className={`pl-7 flex items-center gap-3 py-1 px-3 rounded-lg ${
                    entry.verdict === "通过" && !entry.fallback
                      ? "bg-green-50 dark:bg-green-900/20"
                      : "bg-amber-50 dark:bg-amber-900/20"
                  }`}>
                    <span className={`text-lg font-bold ${
                      entry.fallback ? "text-amber-600" : (entry.score ?? 0) >= 7 ? "text-green-600" : "text-amber-600"
                    }`}>{entry.fallback ? "—" : `${entry.score}/10`}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-xs font-medium ${entry.verdict === "通过" && !entry.fallback ? "text-green-700" : "text-amber-700"}`}>
                        {entry.fallback ? "评估失败 · 未真实评估，默认放行" : entry.verdict === "通过" ? "质量通过" : "需要改进"}
                      </p>
                      {entry.issues && entry.issues.length > 0 && (
                        <p className="text-xs text-muted-foreground truncate">{entry.issues[0]}</p>
                      )}
                    </div>
                  </div>
                );
                if (entry.type === "error") return (
                  <p key={i} className="text-xs text-red-500 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />{entry.message}
                  </p>
                );
                if (entry.type === "warning") return (
                  <p key={i} className="text-xs text-amber-500">{entry.message}</p>
                );
                return null;
              })}
              {isRunningNow && agentLog.length === 0 && (
                <p className="text-xs text-muted-foreground">正在启动 Agent…</p>
              )}
            </div>

            {/* Footer */}
            {agentDone && (
              <div className="px-5 py-4 border-t flex-shrink-0">
                {agentDone.success ? (
                  <div>
                    <p className="text-sm font-medium text-green-600 mb-3">
                      草稿「{agentDone.title}」已保存，图片后台生成中
                    </p>
                    <Button
                      size="sm"
                      className="w-full gap-2"
                      onClick={() => {
                        setAgentLog([]);
                        setAgentDone(null);
                        setTab("contents");
                        fetchContents();
                      }}
                    >
                      <FileText className="w-3.5 h-3.5" />查看内容
                    </Button>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm text-red-600 mb-3">{agentDone.error}</p>
                    <Button
                      size="sm" variant="outline" className="w-full"
                      onClick={() => { setAgentLog([]); setAgentDone(null); }}
                    >关闭</Button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Header */}
      <header className="border-b bg-card/90 backdrop-blur-sm sticky top-0 z-50 shadow-sm">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Link to="/accounts">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  账号列表
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-indigo-400 to-purple-500 rounded-lg flex items-center justify-center text-white font-bold text-sm">
                  {(profile?.nickname || profile?.username || "?")[0].toUpperCase()}
                </div>
                <div>
                  <div className="font-semibold text-sm">{profile?.nickname || profile?.username}</div>
                  {profile?.theme && (
                    <div className="text-xs text-muted-foreground">{profile.theme}</div>
                  )}
                </div>
              </div>
            </div>

            {/* Tab 切换 */}
            <div className="flex items-center bg-muted rounded-lg p-1 gap-1">
              {([
                { id: "contents", label: "内容", icon: FileText },
                { id: "topics",   label: "选题", icon: TrendingUp },
                { id: "config",   label: "配置", icon: Settings },
              ] as const).map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                    tab === id
                      ? "bg-card shadow-sm text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="w-3.5 h-3.5" />
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6 max-w-4xl">
        {/* ═══ 选题 Tab ═══════════════════════════════════════ */}
        {tab === "topics" && (
          <div className="space-y-6">
            {/* 账号定位提示 */}
            {!profile?.theme && (
              <div className="flex items-center gap-3 p-4 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-xl">
                <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-300">账号定位未设定</p>
                  <p className="text-xs text-amber-700 dark:text-amber-400">
                    先到「配置」tab 和小媒对话设定账号主题，选题质量会更高
                  </p>
                </div>
                <Button size="sm" variant="outline" className="text-amber-700 border-amber-300 flex-shrink-0"
                  onClick={() => setTab("config")}>
                  去配置
                </Button>
              </div>
            )}

            {/* 搜索区 */}
            <Card className="border-2">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Search className="w-4 h-4 text-indigo-500" />
                  搜索选题热点
                </CardTitle>
                <CardDescription>输入关键词，AI 综合多平台数据为你推荐 8 个选题角度</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex gap-2">
                  <Input
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    placeholder="输入关键词搜索，或点击下方推荐词..."
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    className="flex-1"
                  />
                  <Button
                    onClick={handleSearch}
                    disabled={!keyword.trim() || isSearching}
                    className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 flex-shrink-0"
                  >
                    {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                    {isSearching ? "搜索中..." : "搜索"}
                  </Button>
                </div>

                {/* 平台选择 + 实时搜索状态 */}
                <div className="flex flex-wrap gap-2">
                  <span className="text-xs text-muted-foreground self-center">来源平台：</span>
                  {PLATFORMS.map((p) => {
                    const st = platformStatus[p.id];
                    const cnt = platformCounts[p.id];
                    return (
                      <button
                        key={p.id}
                        onClick={() => !isSearching && setSelectedPlatforms((prev) =>
                          prev.includes(p.id) ? prev.filter((x) => x !== p.id) : [...prev, p.id]
                        )}
                        className={`text-xs px-2.5 py-1 rounded-full border transition-all flex items-center gap-1 ${
                          selectedPlatforms.includes(p.id)
                            ? `${p.color} border-transparent font-medium`
                            : "bg-muted text-muted-foreground border-transparent"
                        }`}
                      >
                        {st === "loading" && <Loader2 className="w-3 h-3 animate-spin" />}
                        {st === "done" && <CheckCircle2 className="w-3 h-3 text-green-500" />}
                        {st === "error" && <span className="text-red-400">✕</span>}
                        {p.label}
                        {st === "done" && cnt !== undefined && (
                          <span className="opacity-60">·{cnt}</span>
                        )}
                      </button>
                    );
                  })}
                  {isSearching && Object.values(platformStatus).every(s => s === 'done') && (
                    <span className="text-xs text-muted-foreground self-center flex items-center gap-1">
                      <Loader2 className="w-3 h-3 animate-spin" />AI 综合分析中...
                    </span>
                  )}
                </div>

                {/* ── 平台原始搜索结果网格（搜索中/完成后始终显示） ── */}
                {showRawResults && selectedPlatforms.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-muted-foreground flex items-center gap-1.5">
                        各平台搜索结果
                        {isSearching && Object.values(platformStatus).every(s => s === 'done' || s === 'error') && (
                          <span className="flex items-center gap-1 text-indigo-500">
                            <Loader2 className="w-3 h-3 animate-spin" />AI 综合分析中...
                          </span>
                        )}
                      </span>
                      <button onClick={() => setShowRawResults(false)} className="text-[10px] text-muted-foreground hover:text-foreground">收起</button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {selectedPlatforms.map(pid => {
                        const p = PLATFORMS.find(x => x.id === pid);
                        if (!p) return null;
                        const st = platformStatus[pid];
                        const items = platformItems[pid] || [];
                        const isAi = platformAiGenerated[pid];
                        return (
                          <div key={pid} className="rounded-xl border bg-background overflow-hidden flex flex-col">
                            {/* 平台 header */}
                            <div className={`flex items-center gap-1.5 px-2.5 py-2 border-b ${p.color} bg-opacity-20`}>
                              {st === "loading" && <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />}
                              {st === "done" && <CheckCircle2 className="w-3 h-3 text-green-500 flex-shrink-0" />}
                              {st === "error" && <span className="text-red-400 text-xs">✕</span>}
                              <span className="text-xs font-semibold">{p.label}</span>
                              {isAi && (
                                <span className="text-[9px] px-1 py-0.5 rounded bg-purple-100 text-purple-600 dark:bg-purple-900/40 dark:text-purple-300 flex-shrink-0">AI生成</span>
                              )}
                              {items.length > 0 && (
                                <span className="text-[10px] text-muted-foreground ml-auto">{items.length} 条</span>
                              )}
                            </div>
                            {/* 内容列表 */}
                            <div className="overflow-y-auto max-h-48 divide-y">
                              {st === "loading" && items.length === 0 && (
                                <div className="px-2.5 py-3 space-y-2">
                                  {[1,2,3].map(i => (
                                    <div key={i} className="h-3 bg-muted rounded animate-pulse" style={{width: `${70 + i * 8}%`}} />
                                  ))}
                                </div>
                              )}
                              {st === "error" && (
                                <div className="px-2.5 py-3 text-[10px] text-muted-foreground">搜索失败</div>
                              )}
                              {items.map((item, i) => (
                                <div
                                  key={i}
                                  className="flex items-start gap-1.5 px-2.5 py-1.5 hover:bg-muted/30 transition-colors cursor-pointer"
                                  onClick={() => openDetail(pid, item)}
                                >
                                  <span className="text-[10px] text-muted-foreground mt-0.5 w-3.5 flex-shrink-0 text-right">{i + 1}</span>
                                  <span className="text-[11px] flex-1 leading-snug">{item.title}</span>
                                  {item.hot_value && item.hot_value !== "0" && (
                                    <span className="text-[9px] text-orange-500 flex-shrink-0 mt-0.5">🔥{item.hot_value}</span>
                                  )}
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* ── 详情面板（点击搜索结果后弹出） ── */}
                {detailPanel && (
                  <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setDetailPanel(null)}>
                    <div className="w-full max-w-md h-full bg-background border-l shadow-2xl flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
                      {/* 面板 header */}
                      <div className="flex items-center justify-between px-4 py-3 border-b">
                        <span className="text-sm font-semibold truncate flex-1">{detailPanel.item.title}</span>
                        <button onClick={() => setDetailPanel(null)} className="ml-2 text-muted-foreground hover:text-foreground text-lg leading-none">✕</button>
                      </div>
                      {/* 面板内容 */}
                      <div className="flex-1 overflow-y-auto p-4 space-y-4">
                        {detailLoading && (
                          <div className="space-y-3">
                            {[1,2,3,4].map(i => <div key={i} className="h-4 bg-muted rounded animate-pulse" style={{width:`${60+i*10}%`}} />)}
                          </div>
                        )}
                        {detailData?.error && <p className="text-sm text-red-500">{detailData.error}</p>}
                        {detailData && !detailData.error && detailPanel.platform === "xiaohongshu" && (
                          <>
                            {/* 作者信息 */}
                            {detailData.author && (
                              <div className="flex items-center gap-2">
                                {detailData.avatar && <img src={detailData.avatar} className="w-8 h-8 rounded-full object-cover" alt="" />}
                                <div>
                                  <p className="text-sm font-medium">{detailData.author}</p>
                                  {detailData.ip_location && <p className="text-xs text-muted-foreground">{detailData.ip_location}</p>}
                                </div>
                              </div>
                            )}
                            {/* 互动数据 */}
                            <div className="flex gap-4 text-xs text-muted-foreground">
                              {detailData.liked_count && <span>❤️ {detailData.liked_count}</span>}
                              {detailData.comment_count && <span>💬 {detailData.comment_count}</span>}
                              {detailData.collected_count && <span>⭐ {detailData.collected_count}</span>}
                            </div>
                            {/* 图片 */}
                            {detailData.images?.length > 0 && (
                              <div className="flex gap-2 overflow-x-auto pb-1">
                                {detailData.images.map((img: string, i: number) => (
                                  <img key={i} src={img} className="h-32 w-auto rounded-lg flex-shrink-0 object-cover" alt="" />
                                ))}
                              </div>
                            )}
                            {/* 正文 */}
                            {detailData.desc && (
                              <div className="text-sm leading-relaxed whitespace-pre-wrap">{detailData.desc}</div>
                            )}
                            {/* 评论 */}
                            {detailData.comments?.length > 0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground">热门评论</p>
                                {detailData.comments.map((c: any, i: number) => (
                                  <div key={i} className="text-xs bg-muted/40 rounded-lg px-3 py-2">
                                    <span className="font-medium">{c.author}：</span>{c.content}
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                        {/* B站详情 */}
                        {detailData && !detailData.error && detailPanel.platform === "bilibili" && (
                          <>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              <span className="font-medium text-foreground">{detailData.author}</span>
                              {detailData.view > 0 && <span>▶ {detailData.view.toLocaleString()}</span>}
                              {detailData.reply > 0 && <span>💬 {detailData.reply.toLocaleString()}</span>}
                            </div>
                            {detailData.desc && detailData.desc !== "-" && (
                              <div>
                                <p className="text-xs font-medium text-muted-foreground mb-1">简介</p>
                                <div className="text-sm leading-relaxed whitespace-pre-wrap">{detailData.desc}</div>
                              </div>
                            )}
                            {detailData.comments?.length > 0 && (
                              <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground">热门评论</p>
                                {detailData.comments.map((c: any, i: number) => (
                                  <div key={i} className="text-xs bg-muted/40 rounded-lg px-3 py-2">
                                    <span className="font-medium">{c.author}</span>
                                    {c.like > 0 && <span className="text-muted-foreground ml-1">👍{c.like}</span>}
                                    <p className="mt-0.5">{c.content}</p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                        {/* 微信文章详情 */}
                        {detailData && detailPanel.platform === "weixin" && (
                          <>
                            {(detailData.account || detailData.author || detailData.pub_time) && (
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                {(detailData.account || detailData.author) && (
                                  <span className="font-medium text-foreground">{detailData.account || detailData.author}</span>
                                )}
                                {detailData.pub_time && <span>{detailData.pub_time}</span>}
                              </div>
                            )}
                            {detailData.snippet && (
                              <div className="text-sm leading-relaxed text-muted-foreground italic border-l-2 border-green-300 pl-3">{detailData.snippet}</div>
                            )}
                            {detailData.content && (
                              <div className="text-sm leading-relaxed whitespace-pre-wrap">{detailData.content}</div>
                            )}
                            {!detailData.snippet && !detailData.content && (
                              <p className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
                                Sogou 防爬虫拦截了重定向，无法预览全文。点击「打开原文」在浏览器中阅读。
                              </p>
                            )}
                          </>
                        )}
                        {/* 微博详情 */}
                        {detailData && detailPanel.platform === "weibo" && (
                          <>
                            {detailData.hot_value && (
                              <div className="flex items-center gap-2">
                                <span className="text-xs bg-orange-50 dark:bg-orange-950/30 text-orange-600 rounded px-2 py-0.5">
                                  🔥 热度 {detailData.hot_value}
                                </span>
                              </div>
                            )}
                            {detailData.posts?.length > 0 ? (
                              <div className="space-y-2">
                                <p className="text-xs font-medium text-muted-foreground">相关微博</p>
                                {detailData.posts.map((p: any, i: number) => (
                                  <div key={i} className="text-xs bg-muted/40 rounded-lg px-3 py-2">
                                    {p.author && <span className="font-medium">{p.author}</span>}
                                    {p.likes && <span className="text-muted-foreground ml-1">👍{p.likes}</span>}
                                    <p className="mt-0.5 leading-relaxed">{p.content}</p>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
                                微博搜索页需要登录才能查看内容。在 .env 配置 WEIBO_COOKIE 后可自动获取帖子。点击「打开原文」在浏览器查看。
                              </p>
                            )}
                          </>
                        )}
                        {/* 百度详情 */}
                        {detailData && detailPanel.platform === "baidu" && (
                          <>
                            {detailData.title && detailData.title !== detailPanel.item.title && (
                              <p className="text-sm font-medium">{detailData.title}</p>
                            )}
                            {detailData.snippet && (
                              <div className="text-sm leading-relaxed text-muted-foreground italic border-l-2 border-blue-300 pl-3">{detailData.snippet}</div>
                            )}
                            {detailData.content && (
                              <div className="text-sm leading-relaxed whitespace-pre-wrap">{detailData.content}</div>
                            )}
                            {(detailData.ai_item || detailData.fetch_failed) && !detailData.snippet && !detailData.content && (
                              <p className="text-xs text-muted-foreground bg-muted/40 rounded-lg px-3 py-2">
                                {detailData.ai_item
                                  ? "AI 模拟生成的结果，无原始链接。百度触发了反爬虫机制，建议换个关键词重新搜索。"
                                  : "无法提取文章正文（目标网站结构不支持），请点击「打开原文」在浏览器阅读。"}
                              </p>
                            )}
                          </>
                        )}
                        {/* 无详情时仅显示原始标题和跳转 */}
                        {!detailLoading && !detailData && detailPanel.item.url && (
                          <p className="text-sm text-muted-foreground">暂不支持此平台预览详情</p>
                        )}
                      </div>
                      {/* 跳转按钮 */}
                      {detailPanel.item.url && (
                        <div className="px-4 py-3 border-t">
                          <a href={detailPanel.item.url} target="_blank" rel="noopener noreferrer"
                            className="block w-full text-center text-sm py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity">
                            打开原文 →
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* ── 选题类型（只读，来自小媒配置对话） ── */}
                <TopicTypeField
                  value={profile?.topic_type || ""}
                  onGoConfig={() => setTab("config")}
                />

                {/* 有选题词时显示快捷点击条（只读） */}
                {(profile?.keywords || []).filter((k: string) => !k.startsWith('（') && !k.startsWith('(')).length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {(profile.keywords as string[])
                      .filter((k) => !k.startsWith('（') && !k.startsWith('('))
                      .map((kw) => (
                        <button key={kw} onClick={() => setKeyword(kw)}
                          className="text-xs px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 transition-colors">
                          {kw}
                        </button>
                      ))}
                  </div>
                )}

                {/* AI 推荐关键词 */}
                <div className="border-t pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                      <Sparkles className="w-3 h-3 text-indigo-500" />
                      AI 推荐关键词
                    </span>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 text-xs gap-1 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50"
                      onClick={handleSuggestKeywords}
                      disabled={isSuggestingKw}
                    >
                      {isSuggestingKw
                        ? <><Loader2 className="w-3 h-3 animate-spin" />生成中...</>
                        : <><Wand2 className="w-3 h-3" />换一批</>}
                    </Button>
                  </div>

                  {suggestKwError && (
                    <p className="text-xs text-red-500 py-1">{suggestKwError}</p>
                  )}
                  {isSuggestingKw && suggestedKeywords.length === 0 ? (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      AI 正在分析账号定位，推荐关键词...
                    </div>
                  ) : suggestedKeywords.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {suggestedKeywords.map((kw) => (
                        <button
                          key={kw}
                          onClick={() => setKeyword(kw)}
                          className="text-xs px-2.5 py-1 rounded-full border border-indigo-200 bg-indigo-50 dark:bg-indigo-900/20 text-indigo-600 dark:text-indigo-400 hover:bg-indigo-100 hover:border-indigo-300 transition-all"
                        >
                          {kw}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <button
                      onClick={handleSuggestKeywords}
                      disabled={isSuggestingKw}
                      className="w-full text-xs text-center py-2.5 rounded-lg border-2 border-dashed border-indigo-200 text-indigo-400 hover:border-indigo-300 hover:text-indigo-500 hover:bg-indigo-50/50 transition-all flex items-center justify-center gap-1.5"
                    >
                      <Sparkles className="w-3.5 h-3.5" />
                      {profile?.topic_type
                        ? `根据「${profile.topic_type}」生成一批搜索词`
                        : "让 AI 根据账号主题生成搜索词（先在配置Tab设置选题类型）"
                      }
                    </button>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* 生成结果预览 */}
            {generatedContent && (
              <Card className="border-2 border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-950/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2 text-green-700 dark:text-green-400">
                    <CheckCircle2 className="w-4 h-4" />
                    图文已生成，已保存为草稿
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-3 items-start">
                    {generatedContent.images?.[0] && (
                      <img
                        src={resolveImg(generatedContent.images[0])}
                        alt="封面"
                        className="w-16 h-[85px] rounded-lg object-cover flex-shrink-0"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm mb-1 line-clamp-2">{generatedContent.title}</p>
                      <p className="text-xs text-muted-foreground line-clamp-2">{generatedContent.content}</p>
                    </div>
                  </div>
                  <div className="flex gap-2 mt-3">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 gap-1"
                      onClick={() => navigate(`/create`, {
                        state: {
                          id: generatedContent.id,
                          title: generatedContent.title,
                          content: generatedContent.content,
                          tags: generatedContent.tags,
                          images: generatedContent.images,
                          image_prompts_cn: generatedContent.image_prompts_cn,
                          image_prompts: generatedContent.image_prompts_cn,
                          imagePrompts: generatedContent.image_prompts_cn || generatedContent.image_prompts,
                          content_style: generatedContent.content_style || "",
                          image_style: generatedContent.image_style || "",
                        }
                      })}
                    >
                      <Edit className="w-3.5 h-3.5" />编辑
                    </Button>
                    <Button
                      size="sm"
                      className="flex-1 gap-1 bg-green-600 hover:bg-green-700"
                      onClick={() => { setTab("contents"); setGeneratedContent(null); fetchContents(); }}
                    >
                      <FileText className="w-3.5 h-3.5" />查看草稿
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 选题列表 */}
            {topics.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-500" />
                    AI 推荐选题
                    <span className="text-xs font-normal text-muted-foreground">
                      {topics.filter(t => t.status !== "skipped" && t.status !== "used").length} 个可用
                    </span>
                  </h3>
                  <div className="flex items-center gap-2">
                    {showRawResults ? (
                      <button onClick={() => setShowRawResults(false)} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                        收起原始数据
                      </button>
                    ) : (
                      <button onClick={() => setShowRawResults(true)} className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1">
                        查看原始数据
                      </button>
                    )}
                    <Button size="sm" variant="ghost" className="gap-1 text-xs" onClick={handleSearch}>
                      <RefreshCw className="w-3 h-3" />换一批
                    </Button>
                  </div>
                </div>
                <div className="grid sm:grid-cols-2 gap-3">
                  {topics
                    .filter((t) => t.status !== "skipped")
                    .map((topic) => (
                      <TopicCard
                        key={topic.id}
                        topic={topic}
                        isGenerating={generatingTopicId === topic.id}
                        onSelect={() => handleGenerateFromTopic(topic.id)}
                        onSkip={() => handleSkipTopic(topic.id)}
                      />
                    ))}
                </div>
              </div>
            )}

            {/* 空状态 */}
            {topics.length === 0 && !isSearching && (
              <div className="text-center py-16 text-muted-foreground">
                <TrendingUp className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm">输入关键词，发现适合你账号的选题热点</p>
              </div>
            )}
          </div>
        )}

        {/* ═══ 内容 Tab ═══════════════════════════════════════ */}
        {tab === "contents" && (
          <div>
            <div className="flex items-center justify-between mb-5">
              <h2 className="font-semibold">内容草稿 &amp; 已发布</h2>

              {!isSelectMode ? (
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" className="gap-1.5 text-red-600 border-red-200 hover:bg-red-50"
                    onClick={enterSelectMode}>
                    <Trash2 className="w-3.5 h-3.5" />批量删除
                  </Button>
                  <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setTab("topics")}>
                    <Sparkles className="w-3.5 h-3.5" />去选题生成
                  </Button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <button className="text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => setSelectedIds(new Set(contents.filter(c=>c.status==="draft").map(c=>c.id)))}>
                    全选草稿
                  </button>
                  <Button size="sm" variant="destructive" className="gap-1.5"
                    onClick={handleBatchDelete} disabled={isDeletingBatch || selectedIds.size === 0}>
                    {isDeletingBatch ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    {selectedIds.size > 0 ? `删除 ${selectedIds.size} 篇` : "删除"}
                  </Button>
                  <button className="text-xs text-muted-foreground hover:text-foreground" onClick={exitSelectMode}>
                    取消
                  </button>
                </div>
              )}
            </div>

            {isLoadingContents ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              </div>
            ) : contents.length === 0 ? (
              <div className="text-center py-16 text-muted-foreground">
                <FileText className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm mb-3">还没有内容</p>
                <Button size="sm" onClick={() => setTab("topics")} className="gap-2">
                  <TrendingUp className="w-3.5 h-3.5" />去选题
                </Button>
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 gap-4">
                {contents.map((item) => (
                  <div key={item.id} className={`relative rounded-xl transition-all ${isSelectMode && selectedIds.has(item.id) ? "ring-2 ring-indigo-400" : ""}`}>
                    {/* 选择模式：右上角 checkbox，不遮标题 */}
                    {isSelectMode && (
                      <input
                        type="checkbox"
                        checked={selectedIds.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                        onClick={e => e.stopPropagation()}
                        className="absolute top-3 right-3 z-10 w-4 h-4 cursor-pointer accent-indigo-500"
                      />
                    )}
                  <ContentCard
                    key={item.id}
                    item={item}
                    onPreview={() => isSelectMode ? toggleSelect(item.id) : navigate("/preview", {
                      state: {
                        id: item.id,
                        title: item.title,
                        content: item.content,
                        images: item.images,
                        tags: item.tags,
                        image_prompts: item.image_prompts || [],
                        imagePrompts: item.image_prompts || [],
                      }
                    })}
                    onEdit={() => navigate(`/create`, {
                      state: {
                        id: item.id,
                        title: item.title,
                        content: item.content,
                        tags: item.tags,
                        images: item.images,
                        imagePrompts: item.image_prompts || [],
                        content_style: profileForm.content_style || "",
                        image_style: profileForm.image_style || "",
                      }
                    })}
                  />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ═══ 配置 Tab ═══════════════════════════════════════ */}
        {tab === "config" && (
          <div className="space-y-6">
          <div className="grid lg:grid-cols-2 gap-6">
            {/* 左：和小媒对话配置 */}
            <div>
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <MessageCircle className="w-4 h-4 text-indigo-500" />
                账号管家小媒
                <span className="text-xs font-normal text-muted-foreground">聊定位 · 改配置 · 直接发帖，都在这</span>
              </h3>

              <div className="border-2 rounded-xl overflow-hidden">
                {/* 消息区 */}
                <div className="h-80 overflow-y-auto p-4 space-y-3 bg-muted/20">
                  {chatMessages.map((msg, i) => {
                    const isLastAssistant = msg.role === "assistant" &&
                      i === chatMessages.map((m, idx) => m.role === "assistant" ? idx : -1).filter(x => x >= 0).slice(-1)[0];
                    return (
                    <div key={i}>
                      {msg.role === "assistant" && msg.activity && msg.activity.length > 0 &&
                        renderChatActivity(msg.activity, false)}
                      <div
                        className={`flex gap-2 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
                      >
                        {msg.role === "assistant" && (
                          <div className="w-7 h-7 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-sm flex-shrink-0">
                            🌀
                          </div>
                        )}
                        <div
                          className={`max-w-[80%] rounded-xl px-3 py-2 text-sm leading-relaxed whitespace-pre-line ${
                            msg.role === "user"
                              ? "bg-indigo-500 text-white"
                              : "bg-card border shadow-sm"
                          }`}
                        >
                          {msg.message}
                        </div>
                      </div>
                      {isLastAssistant && msg.options && msg.options.length > 0 && !isChatting && (
                        <div className="flex flex-wrap gap-2 mt-2 ml-9">
                          {msg.options.map((opt) => (
                            <button
                              key={opt}
                              onClick={() => handleChatWithMessage(opt)}
                              className="text-xs px-3 py-1.5 rounded-full border border-indigo-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-all"
                            >
                              {opt}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                    );
                  })}
                  {isChatting && (
                    <div>
                      {chatActivity.length > 0 && renderChatActivity(chatActivity, true)}
                      <div className="flex gap-2">
                        <div className="w-7 h-7 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-full flex items-center justify-center text-sm">🌀</div>
                        <div className="bg-card border rounded-xl px-3 py-2">
                          <div className="flex gap-1">
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.15s" }} />
                            <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0.3s" }} />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>

                {/* 输入区 */}
                <div className="border-t p-3 flex gap-2 bg-card">
                  <Input
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    placeholder="聊定位、改配置、或说「发一篇试试」..."
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleChat()}
                    className="flex-1 border-0 bg-muted/50 focus-visible:ring-1"
                  />
                  <Button
                    size="icon"
                    onClick={handleChat}
                    disabled={!chatInput.trim() || isChatting}
                    className="bg-indigo-500 hover:bg-indigo-600 flex-shrink-0"
                  >
                    <Send className="w-4 h-4" />
                  </Button>
                </div>
              </div>

              <p className="text-xs text-muted-foreground mt-2">
                💡 小媒会在对话中直接更新右侧配置，无需手动保存。
                <button
                  className="text-indigo-500 hover:underline ml-1 disabled:opacity-50"
                  onClick={handleSaveConfig}
                  disabled={isSavingConfig || chatMessages.length <= 1}
                >
                  {isSavingConfig ? "正在提取..." : configSaved ? "✅ 已提取" : "从历史对话重新提取配置"}
                </button>
              </p>
            </div>

            {/* 右：手动填写配置 */}
            <div>
              <h3 className="font-semibold mb-4 flex items-center gap-2">
                <Settings className="w-4 h-4 text-indigo-500" />
                手动填写配置
              </h3>

              <div className="space-y-4">
                <div>
                  <Label className="text-xs">账号主题</Label>
                  <Input
                    value={profileForm.theme}
                    onChange={(e) => setProfileForm(p => ({ ...p, theme: e.target.value }))}
                    placeholder="如：职场穿搭 / 健身打卡 / 精致下午茶"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">目标受众</Label>
                  <Input
                    value={profileForm.target_audience}
                    onChange={(e) => setProfileForm(p => ({ ...p, target_audience: e.target.value }))}
                    placeholder="如：25-35岁都市白领，爱喝咖啡"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">内容风格</Label>
                  <Input
                    value={profileForm.content_style}
                    onChange={(e) => setProfileForm(p => ({ ...p, content_style: e.target.value }))}
                    placeholder="如：轻松真实，不要广告感"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">配图风格 <span className="text-muted-foreground font-normal">（每篇帖子的图片怎么安排）</span></Label>
                  <Textarea
                    value={profileForm.image_style}
                    onChange={(e) => setProfileForm(p => ({ ...p, image_style: e.target.value }))}
                    placeholder={"例：封面效果图 + 3张过程图 + 最后整体展示\n或：全部过程实拍\n或：只拍最终效果，不要过程图"}
                    className="mt-1 min-h-[72px] text-sm"
                  />
                </div>
                <div>
                  <Label className="text-xs">
                    选题类型
                    <span className="text-muted-foreground font-normal ml-1">（通常由小媒对话自动提取，也可手动填写）</span>
                  </Label>
                  <Input
                    value={profileForm.topic_type}
                    onChange={(e) => setProfileForm(p => ({ ...p, topic_type: e.target.value }))}
                    placeholder="如：西餐菜品 / 通勤穿搭场景 / 上海咖啡探店"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">
                    具体选题词
                    <span className="text-muted-foreground font-normal ml-1">（从选题类型生成，逗号分隔）</span>
                  </Label>
                  <Input
                    value={profileForm.keywords}
                    onChange={(e) => setProfileForm(p => ({ ...p, keywords: e.target.value }))}
                    placeholder="如：芝士焗虾, 意式烩饭, 黑松露意面, 法式焦糖布丁"
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label className="text-xs">文案要求（每行一条）</Label>
                  <Textarea
                    value={profileForm.requirements}
                    onChange={(e) => setProfileForm(p => ({ ...p, requirements: e.target.value }))}
                    placeholder={"不要用网络流行语\n要像真实探店分享\n每篇必须提到环境和价格"}
                    className="mt-1 min-h-[100px] text-sm"
                  />
                </div>
                <Button
                  className="w-full gap-2"
                  onClick={handleSaveProfileForm}
                  disabled={isSavingConfig}
                >
                  {isSavingConfig ? (
                    <><Loader2 className="w-4 h-4 animate-spin" />保存中...</>
                  ) : configSaved ? (
                    <><CheckCircle2 className="w-4 h-4" />已保存</>
                  ) : (
                    <><Save className="w-4 h-4" />保存配置</>
                  )}
                </Button>
              </div>
            </div>
          </div>
          {/* 自动运营面板 */}
          <div className="mt-8 border-t pt-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <Bot className="w-4 h-4 text-purple-500" />
              Agent 自动运营
            </h3>

            <div className="space-y-5">
              {/* 开关 */}
              <div className="flex items-center justify-between p-4 rounded-xl border-2 bg-card">
                <div>
                  <p className="font-medium text-sm">自动运营开关</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    开启后 Agent 会按频率自动搜选题、生成图文，存入草稿
                  </p>
                  {autoConfig.last_auto_run && (
                    <p className="text-xs text-muted-foreground mt-1">
                      上次运行：{new Date(autoConfig.last_auto_run).toLocaleString("zh-CN")}
                      {autoConfig.next_run && autoConfig.next_run !== "尽快" && (
                        <span className="ml-2">下次：{new Date(autoConfig.next_run).toLocaleString("zh-CN")}</span>
                      )}
                    </p>
                  )}
                </div>
                <Switch
                  checked={autoConfig.auto_enabled}
                  onCheckedChange={handleToggleAuto}
                />
              </div>

              {/* 频率 + 篇数（仅开启时显示） */}
              {autoConfig.auto_enabled && (
                <div className="grid grid-cols-2 gap-4 p-4 rounded-xl border bg-muted/20">
                  <div>
                    <Label className="text-xs">运营频率</Label>
                    <select
                      className="w-full h-9 mt-1 px-3 rounded-md border border-input bg-background text-sm"
                      value={autoConfig.auto_frequency}
                      onChange={e => setAutoConfig(c => ({ ...c, auto_frequency: e.target.value }))}
                    >
                      <option value="daily">每天</option>
                      <option value="every_2_days">隔天</option>
                      <option value="weekly">每周</option>
                    </select>
                  </div>
                  <div>
                    <Label className="text-xs">每次产出篇数</Label>
                    <select
                      className="w-full h-9 mt-1 px-3 rounded-md border border-input bg-background text-sm"
                      value={autoConfig.auto_count}
                      onChange={e => setAutoConfig(c => ({ ...c, auto_count: parseInt(e.target.value) }))}
                    >
                      {[1, 2, 3, 5].map(n => <option key={n} value={n}>{n} 篇</option>)}
                    </select>
                  </div>
                  <div className="col-span-2">
                    <Button size="sm" variant="outline" className="w-full gap-2" onClick={handleSaveAutoFrequency}>
                      <Save className="w-3.5 h-3.5" />保存频率设置
                    </Button>
                  </div>
                </div>
              )}

              {/* 立即运行 */}
              <Button
                className="w-full gap-2 bg-gradient-to-r from-purple-500 to-indigo-600 hover:from-purple-600 hover:to-indigo-700"
                onClick={handleRunNow}
                disabled={isRunningNow}
              >
                {isRunningNow
                  ? <><Loader2 className="w-4 h-4 animate-spin" />Agent 正在工作中（30-90秒）...</>
                  : <><Play className="w-4 h-4" />立即运行一次（搜选题→生成图文→存草稿）</>
                }
              </Button>

              {/* 运行结果 */}
              {autoRunResult && (
                <div className={`p-4 rounded-xl border text-sm ${autoRunResult.error ? "bg-red-50 border-red-200 text-red-700" : "bg-green-50 border-green-200 text-green-700"}`}>
                  {autoRunResult.error ? (
                    <p>运行失败：{autoRunResult.error}</p>
                  ) : (
                    <>
                      <p className="font-medium mb-2">产出 {autoRunResult.produced} 篇草稿：</p>
                      {autoRunResult.contents?.map((c: any) => (
                        <p key={c.id} className="text-xs">· 《{c.title}》</p>
                      ))}
                      <p className="text-xs mt-2 text-green-600">已保存到「内容」Tab，可以去编辑和发布</p>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
          </div>
        )}
      </div>
    </div>
  );
}
