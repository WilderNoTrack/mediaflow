import { useState, useRef, useEffect } from "react";
import { useNavigate, useLocation } from "react-router";
import { notifyJobStarted } from "@/components/GenerationProgress";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import {
  ArrowLeft,
  Save,
  Send,
  Eye,
  Loader2,
  Image as ImageIcon,
  X,
  AlertCircle,
  CheckCircle2,
  Tag,
  PenTool,
  FileText,
  Sparkles,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { PublishDialog } from "../../components/PublishDialog";
import { t } from "../../i18n";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface ImagePreview {
  id: string;
  url: string;
  file?: File;
}

export function CreatePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const draftData = location.state as {
    id?: string;
    title?: string;
    content?: string;
    tags?: string[];
    images?: string[];
    imagePrompts?: string[];
    content_style?: string;
    image_style?: string;
  } | null;

  const [title, setTitle] = useState(draftData?.title || "");
  const [content, setContent] = useState(draftData?.content || "");
  const [tags, setTags] = useState(draftData?.tags?.join(", ") || "");
  const resolveImg = (url: string) => url?.startsWith("/") ? `${API_BASE}${url}` : (url || "");
  const [images, setImages] = useState<ImagePreview[]>(
    draftData?.images?.map((url, index) => ({ id: index.toString(), url: resolveImg(url) })) || []
  );
  // 兼容多种字段名：imagePrompts / image_prompts / image_prompts_cn
  const [imagePrompts, setImagePrompts] = useState<string[]>(() => {
    const d = draftData as any;
    return d?.imagePrompts || d?.image_prompts || d?.image_prompts_cn || [];
  });
  const [bgGenerating, setBgGenerating] = useState<boolean>(!!(draftData as any)?.imagesGenerating);
  const [generatingAll, setGeneratingAll] = useState(false);
  const [perImageGenerating, setPerImageGenerating] = useState<Record<number, boolean>>({});

  // 配图生成中时轮询：以服务端的 image_status 为准，边生成边把已完成的图换上。
  //
  // 生成跑在后台，转圈状态却是组件本地 state，切走再回来就没了。所以这里
  // 每次进页面都先问一次服务端，而不是只信 navigate 带过来的那份快照。
  useEffect(() => {
    const id = draftData?.id;
    if (!id) return;
    let stopped = false;
    let timer: number | undefined;

    const isReal = (u: string) => !!u && !u.includes("placehold.co");

    const check = async () => {
      if (stopped) return;
      try {
        const token = localStorage.getItem("token");
        const res = await fetch(`${API_BASE}/api/contents/${id}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const d = await res.json();
          const imgs: string[] = d.images || [];
          if (imgs.length) {
            setImages(imgs.map((url, i) => ({ id: String(i), url: resolveImg(url) })));
          }
          if (d.image_prompts?.length) setImagePrompts(d.image_prompts);

          const pending = d.image_status === "pending";
          setBgGenerating(pending);
          // 尚未产出真实图片的槽位继续显示转圈
          setPerImageGenerating(
            pending
              ? imgs.reduce((acc: Record<number, boolean>, u, i) => {
                  if (!isReal(u)) acc[i] = true;
                  return acc;
                }, {})
              : {}
          );
          if (!pending) return;   // 已收尾，不再轮询
        }
      } catch {
        // 后端暂时不可用，下一轮再试
      }
      if (!stopped) timer = window.setTimeout(check, 5000);
    };

    check();
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [draftData?.id]);

  const [isSaving, setIsSaving] = useState(false);
  const [generatingImageIdx, setGeneratingImageIdx] = useState<number | null>(null);
  const [lightboxIdx, setLightboxIdx] = useState<number | null>(null);
  const [currentImgIdx, setCurrentImgIdx] = useState(0);
  const lbTouchX = useRef(0);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // AI 修改
  const [showAiPanel, setShowAiPanel] = useState(false);
  const [aiReq, setAiReq] = useState("");
  const [isAiEditing, setIsAiEditing] = useState(false);

  const QUICK_REQS = [
    "让标题更吸引人",
    "缩短正文，控制在300字内",
    "语气更轻松活泼",
    "加入更多 emoji",
    "重新生成标签",
    "让内容更有干货感",
    "重新规划配图说明，按步骤拆分",
    "配图改成只拍成品",
  ];

  const handleAiEdit = async () => {
    if (!aiReq.trim()) return;
    if (!title.trim() && !content.trim()) {
      setError("请先填写内容再使用 AI 修改");
      return;
    }
    setIsAiEditing(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE}/api/contents/ai-modify`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          title,
          content,
          tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
          image_prompts: imagePrompts,
          requirement: aiReq,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        if (data.title) setTitle(data.title);
        if (data.content) setContent(data.content);
        if (data.tags && Array.isArray(data.tags)) setTags(data.tags.join(", "));
        if (data.image_prompts && Array.isArray(data.image_prompts)) setImagePrompts(data.image_prompts);
        setAiReq("");
        setShowAiPanel(false);
        setSuccess("AI 修改完成！");
        setTimeout(() => setSuccess(""), 3000);
      } else {
        const e = await res.json();
        setError(e.detail || "AI 修改失败");
      }
    } catch {
      setError("网络错误，请检查服务是否启动");
    } finally {
      setIsAiEditing(false);
    }
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    const newImages: ImagePreview[] = Array.from(files).map((file) => ({
      id: Math.random().toString(36).substring(7),
      url: URL.createObjectURL(file),
      file,
    }));
    setImages([...images, ...newImages]);
  };

  const handleRemoveImage = (id: string) => setImages(images.filter((img) => img.id !== id));

  const handleGenerateAllImages = async () => {
    const validPrompts = imagePrompts.filter((p) => p?.trim());
    if (!validPrompts.length) { setError("请先填写图片提示词"); return; }
    setGeneratingAll(true);
    setError("");
    const token = localStorage.getItem("token");

    // 初始化每张图的 loading 状态
    const initGenerating: Record<number, boolean> = {};
    imagePrompts.forEach((_, i) => { if (imagePrompts[i]?.trim()) initGenerating[i] = true; });
    setPerImageGenerating(initGenerating);
    // 让顶部全局进度条立刻感知，不用等它下一轮轮询
    notifyJobStarted();

    try {
      const res = await fetch(`${API_BASE}/api/contents/generate-all-images`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          prompts: imagePrompts,
          content_id: draftData?.id || "",
          topic_title: title,
          content_style: (draftData as any)?.content_style || "",
          image_style: (draftData as any)?.image_style || "",
        }),
      });
      if (!res.ok || !res.body) { setError("批量生成失败"); setGeneratingAll(false); setPerImageGenerating({}); return; }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let newImages = [...images];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let ev: any;
          try { ev = JSON.parse(line.slice(6)); } catch { continue; }
          if (ev.type === "complete") continue;
          const { index, status, url } = ev;
          // 更新该图片 loading 状态
          setPerImageGenerating((prev) => { const n = { ...prev }; delete n[index]; return n; });
          if (status === "done" && url) {
            const fullUrl = `${API_BASE}${url}`;
            if (index < newImages.length) {
              newImages = newImages.map((img, i) => i === index ? { ...img, url: fullUrl } : img);
            } else {
              while (newImages.length < index) newImages.push({ id: Math.random().toString(36).slice(7), url: "" });
              newImages = [...newImages, { id: Math.random().toString(36).slice(7), url: fullUrl }];
            }
            setImages([...newImages]);
          }
        }
      }
      setSuccess("全部图片生成完成");
      setTimeout(() => setSuccess(""), 3000);
    } catch (e: any) {
      setError(e?.message || "生成失败");
    }
    setGeneratingAll(false);
    setPerImageGenerating({});
  };

  const handleRegenerateImage = async (index: number) => {
    const prompt = imagePrompts[index];
    if (!prompt?.trim()) {
      setError("请先填写这张图的提示词");
      return;
    }
    setGeneratingImageIdx(index);
    setError("");
    // 让顶部全局进度条立刻感知
    notifyJobStarted();
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE}/api/contents/generate-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          prompt,
          topic_title: title,
          content_style: (draftData as any)?.content_style || "",
          image_style: (draftData as any)?.image_style || "",
          // 带上归属，后端才能落库并维护 image_status（进度条据此可见）
          content_id: draftData?.id || "",
          index,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        const newImages = [...images];
        if (index < newImages.length) {
          newImages[index] = { id: newImages[index].id, url: `${API_BASE}${data.url}` };
        } else {
          newImages.push({ id: Math.random().toString(36).slice(7), url: `${API_BASE}${data.url}` });
        }
        setImages(newImages);

        // 用后端返回的扩写提示词更新 textarea
        const newPrompts = [...imagePrompts];
        if (data.prompt_used) {
          while (newPrompts.length <= index) newPrompts.push("");
          newPrompts[index] = data.prompt_used;
          setImagePrompts(newPrompts);
        }

        // 自动保存回数据库（有 id 时）
        if (draftData?.id) {
          try {
            await fetch(`${API_BASE}/api/contents/${draftData.id}`, {
              method: "PUT",
              headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
              body: JSON.stringify({
                title,
                content,
                tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
                images: newImages.map((img) => img.url.replace(API_BASE, "")),
                image_prompts: data.prompt_used ? newPrompts : imagePrompts,
              }),
            });
            setSuccess("图片已更新并自动保存");
            setTimeout(() => setSuccess(""), 2000);
          } catch {
            // 自动保存失败不影响使用，静默忽略
          }
        }
      } else {
        const e = await res.json();
        setError(e.detail || "生成失败");
      }
    } catch {
      setError("网络错误");
    } finally {
      setGeneratingImageIdx(null);
    }
  };

  const handleSaveDraft = async () => {
    if (!title.trim() || !content.trim()) {
      setError(t("标题和内容不能为空"));
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      let imageUrls: string[] = [];

      if (images.length > 0) {
        imageUrls = await Promise.all(
          images.map(async (img) => {
            if (!img.file) return img.url.replace(API_BASE, "");
            const formData = new FormData();
            formData.append("file", img.file);
            const res = await fetch(`${API_BASE}/api/contents/upload`, {
              method: "POST",
              headers: { Authorization: `Bearer ${token}` },
              body: formData,
            });
            if (!res.ok) throw new Error(t("图片上传失败"));
            return (await res.json()).url;
          })
        );
      }

      const body = JSON.stringify({
        title,
        content,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        images: imageUrls,
        image_prompts: imagePrompts,
      });

      const response = draftData?.id
        ? await fetch(`${API_BASE}/api/contents/${draftData.id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body,
          })
        : await fetch(`${API_BASE}/api/contents/`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
            body,
          });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || t("保存失败"));
      }
      setSuccess(t("草稿保存成功！"));
      setTimeout(() => navigate(-1), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("网络错误"));
    } finally {
      setIsSaving(false);
    }
  };

  const handlePreview = () => {
    if (!title.trim() || !content.trim()) {
      setError(t("标题和内容不能为空"));
      return;
    }
    navigate("/preview", {
      state: { title, content, images: images.map((img) => img.url), tags: tags.split(",") },
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card/90 backdrop-blur-sm sticky top-0 z-50 shadow-sm">
        <div className="container mx-auto px-4 py-3">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <Button variant="ghost" size="sm" className="gap-2" onClick={() => navigate(-1)}>
                <ArrowLeft className="w-4 h-4" />
                {t("返回")}
              </Button>
              <div>
                <h1 className="text-lg font-bold">{t("创建内容")}</h1>
              </div>
            </div>
            {/* 右上角操作按钮 */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 border-indigo-200 text-indigo-600 hover:bg-indigo-50"
                onClick={handlePreview}
                disabled={!title.trim() || !content.trim()}
              >
                <Eye className="w-4 h-4" />
                预览
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={handleSaveDraft}
                disabled={isSaving || !title.trim() || !content.trim()}
              >
                {isSaving
                  ? <><Loader2 className="w-4 h-4 animate-spin" />保存中</>
                  : <><Save className="w-4 h-4" />保存草稿</>}
              </Button>
              <Button
                size="sm"
                className="gap-1.5 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                onClick={() => {
                  if (!title.trim() || !content.trim()) { setError(t("标题和内容不能为空")); return; }
                  setError("");
                  setShowPublishDialog(true);
                }}
                disabled={!title.trim() || !content.trim()}
              >
                <Send className="w-4 h-4" />
                发布
              </Button>
            </div>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {error && (
          <Card className="mb-6 border-2 border-red-200 bg-red-50 dark:bg-red-900/20">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-red-600" />
                <p className="text-red-600">{error}</p>
              </div>
            </CardContent>
          </Card>
        )}
        {success && (
          <Card className="mb-6 border-2 border-green-200 bg-green-50 dark:bg-green-900/20">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <CheckCircle2 className="w-5 h-5 text-green-600" />
                <p className="text-green-600">{success}</p>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="grid lg:grid-cols-3 gap-8">
          {/* ── 左侧主内容 ── */}
          <div className="lg:col-span-2 space-y-6">
            <Card className="border-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PenTool className="w-5 h-5 text-indigo-600" />
                  {t("标题")}
                </CardTitle>
                <CardDescription>{t("吸引人的标题能让内容获得更多关注")}</CardDescription>
              </CardHeader>
              <CardContent>
                <Input
                  placeholder={t("输入标题...")}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="text-lg font-medium"
                />
              </CardContent>
            </Card>

            <Card className="border-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-indigo-600" />
                  {t("正文")}
                </CardTitle>
                <CardDescription>{t("撰写优质内容，分享你的见解和故事")}</CardDescription>
              </CardHeader>
              <CardContent>
                <Textarea
                  placeholder={t("开始写作...")}
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  className="min-h-[300px] text-base leading-relaxed"
                />
              </CardContent>
            </Card>

            <Card className="border-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Tag className="w-5 h-5 text-indigo-600" />
                  {t("标签")}
                </CardTitle>
                <CardDescription>{t("用逗号分隔，如：家常菜,快手菜")}</CardDescription>
              </CardHeader>
              <CardContent>
                <Input
                  placeholder="家常菜, 快手菜, 上班族..."
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                />
              </CardContent>
            </Card>

            {/* ── AI 修改面板 ── */}
            <Card className="border-2 border-indigo-200 dark:border-indigo-800">
              <CardHeader
                className="cursor-pointer select-none"
                onClick={() => setShowAiPanel(!showAiPanel)}
              >
                <CardTitle className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-5 h-5 text-indigo-600" />
                    AI 修改
                  </div>
                  {showAiPanel ? (
                    <ChevronUp className="w-4 h-4 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-muted-foreground" />
                  )}
                </CardTitle>
                <CardDescription>告诉 AI 你想如何修改，它会帮你重写标题、正文和标签</CardDescription>
              </CardHeader>

              {showAiPanel && (
                <CardContent className="space-y-4">
                  {/* 快捷要求 */}
                  <div className="flex flex-wrap gap-2">
                    {QUICK_REQS.map((req) => (
                      <button
                        key={req}
                        onClick={() => setAiReq(req)}
                        className={`text-xs px-3 py-1.5 rounded-full border transition-all ${
                          aiReq === req
                            ? "bg-indigo-500 text-white border-transparent"
                            : "bg-muted text-muted-foreground hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200"
                        }`}
                      >
                        {req}
                      </button>
                    ))}
                  </div>

                  {/* 自定义输入 */}
                  <Textarea
                    placeholder="或输入自定义修改要求，如：把正文改成分步骤教程，每步加序号..."
                    value={aiReq}
                    onChange={(e) => setAiReq(e.target.value)}
                    className="min-h-[90px] text-sm"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handleAiEdit();
                    }}
                  />

                  <Button
                    className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                    onClick={handleAiEdit}
                    disabled={isAiEditing || !aiReq.trim()}
                  >
                    {isAiEditing ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        AI 修改中...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4 mr-2" />
                        开始修改（Ctrl+Enter）
                      </>
                    )}
                  </Button>
                </CardContent>
              )}
            </Card>
          </div>

          {/* ── 右侧边栏 ── */}
          <div className="space-y-6">
            <Card className="border-2">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ImageIcon className="w-5 h-5 text-indigo-600" />
                    图片
                  </div>
                  <div className="flex items-center gap-2">
                    {bgGenerating ? (
                      <span className="text-xs text-amber-500 flex items-center gap-1">
                        <Loader2 className="w-3 h-3 animate-spin" />配图生成中...
                      </span>
                    ) : (
                      <span className="text-xs font-normal text-muted-foreground">{images.length}/9</span>
                    )}
                    {imagePrompts.some((p) => p?.trim()) && (
                      <button
                        onClick={handleGenerateAllImages}
                        disabled={generatingAll || generatingImageIdx !== null}
                        title="一键生成全部图片（并行）"
                        className="text-xs px-2 py-1 rounded-md bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-40 flex items-center gap-1 transition-colors"
                      >
                        {generatingAll
                          ? <><Loader2 className="w-3 h-3 animate-spin" />生成中...</>
                          : <><Sparkles className="w-3 h-3" />一键生成</>}
                      </button>
                    )}
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {/* ── 大图预览 ── */}
                {(() => {
                  const totalSlots = Math.max(images.length, imagePrompts.length);
                  const safeIdx = Math.min(currentImgIdx, Math.max(0, totalSlots - 1));
                  const hasImg = safeIdx < images.length;
                  const isGenerating = generatingImageIdx === safeIdx || !!perImageGenerating[safeIdx];
                  return (
                    <div>
                      {/* 主图区 */}
                      <div
                        className="relative w-full rounded-xl overflow-hidden bg-gray-100 cursor-pointer"
                        style={{ aspectRatio: "3/4" }}
                        onClick={() => hasImg && setLightboxIdx(safeIdx)}
                      >
                        {isGenerating ? (
                          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
                            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
                            <p className="text-xs text-muted-foreground">生成中...</p>
                          </div>
                        ) : hasImg ? (
                          <img src={images[safeIdx].url} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center gap-2 text-muted-foreground">
                            <ImageIcon className="w-10 h-10 opacity-30" />
                            <p className="text-xs">第 {safeIdx + 1} 张 · 待生成</p>
                          </div>
                        )}
                        {hasImg && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleRemoveImage(images[safeIdx].id); }}
                            className="absolute top-2 right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>

                      {/* 缩略图横排 */}
                      {totalSlots > 0 && (
                        <div className="flex gap-1.5 mt-2 overflow-x-auto pb-1">
                          {Array.from({ length: totalSlots }).map((_, i) => (
                            <button
                              key={i}
                              onClick={() => setCurrentImgIdx(i)}
                              className={`flex-shrink-0 w-12 h-14 rounded-lg overflow-hidden border-2 transition-all ${
                                i === safeIdx ? "border-indigo-500" : "border-transparent"
                              } ${i < images.length ? "bg-gray-100" : "bg-gray-50 border-dashed border-gray-200"}`}
                            >
                              {generatingImageIdx === i || perImageGenerating[i] ? (
                                <div className="w-full h-full flex items-center justify-center">
                                  <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                                </div>
                              ) : i < images.length ? (
                                <img src={images[i].url} alt="" className="w-full h-full object-cover" />
                              ) : (
                                <div className="w-full h-full flex items-center justify-center text-xs text-gray-300">
                                  {i + 1}
                                </div>
                              )}
                            </button>
                          ))}
                          {/* 上传按钮 */}
                          {images.length < 9 && (
                            <label className="flex-shrink-0 w-12 h-14 rounded-lg border-2 border-dashed border-indigo-200 flex items-center justify-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50 transition-colors">
                              <span className="text-indigo-400 text-xl leading-none">+</span>
                              <input type="file" accept="image/jpeg,image/png" multiple onChange={handleImageUpload} className="hidden" />
                            </label>
                          )}
                        </div>
                      )}

                      {/* 当前图的提示词（完整显示） */}
                      <div className="mt-3">
                        <p className="text-xs text-muted-foreground mb-1.5">
                          第 {safeIdx + 1} 张 · 提示词
                        </p>
                        <div className="flex gap-1.5">
                          <Textarea
                            value={imagePrompts[safeIdx] || ""}
                            onChange={(e) => {
                              const n = [...imagePrompts];
                              while (n.length <= safeIdx) n.push("");
                              n[safeIdx] = e.target.value;
                              setImagePrompts(n);
                            }}
                            placeholder="描述这张图拍什么、从什么角度、什么氛围..."
                            className="flex-1 text-xs min-h-[72px]"
                            style={{ height: "auto", resize: "vertical" }}
                            rows={Math.max(4, Math.ceil((imagePrompts[safeIdx] || "").length / 40))}
                          />
                          <button
                            onClick={() => handleRegenerateImage(safeIdx)}
                            disabled={generatingImageIdx !== null}
                            title="重新生成这张图"
                            className="flex-shrink-0 self-start p-2 rounded-lg border text-indigo-600 border-indigo-200 hover:bg-indigo-50 disabled:opacity-40 transition-colors"
                          >
                            {generatingImageIdx === safeIdx
                              ? <Loader2 className="w-4 h-4 animate-spin" />
                              : <RefreshCw className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })()}

                {/* 无图无提示词时的上传入口 */}
                {images.length === 0 && imagePrompts.length === 0 && (
                  <label className="block">
                    <div className="border-2 border-dashed border-border rounded-lg p-6 text-center hover:border-indigo-500 transition-colors cursor-pointer">
                      <ImageIcon className="w-10 h-10 mx-auto mb-2 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground">点击或拖拽上传图片</p>
                    </div>
                  </label>
                )}

              </CardContent>
            </Card>

          </div>
        </div>
      </div>

      {/* 图片放大查看（支持左右切换） */}
      {lightboxIdx !== null && images[lightboxIdx] && (
        <div
          className="fixed inset-0 z-50 bg-black/92 flex items-center justify-center"
          onClick={() => setLightboxIdx(null)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setLightboxIdx(null);
            if (e.key === "ArrowLeft" && lightboxIdx > 0) setLightboxIdx(lightboxIdx - 1);
            if (e.key === "ArrowRight" && lightboxIdx < images.length - 1) setLightboxIdx(lightboxIdx + 1);
          }}
          onTouchStart={(e) => { lbTouchX.current = e.touches[0].clientX; }}
          onTouchEnd={(e) => {
            const diff = lbTouchX.current - e.changedTouches[0].clientX;
            if (diff > 50 && lightboxIdx < images.length - 1) setLightboxIdx(lightboxIdx + 1);
            if (diff < -50 && lightboxIdx > 0) setLightboxIdx(lightboxIdx - 1);
          }}
          tabIndex={0}
          autoFocus
        >
          {/* 图片本体 */}
          <img
            src={images[lightboxIdx].url}
            alt="放大查看"
            className="max-w-[90vw] max-h-[88vh] rounded-lg object-contain shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          />

          {/* 关闭 */}
          <button
            className="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/20 hover:bg-white/30 text-white flex items-center justify-center"
            onClick={() => setLightboxIdx(null)}
          >
            <X className="w-5 h-5" />
          </button>

          {/* 左箭头 */}
          {lightboxIdx > 0 && (
            <button
              className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 text-white flex items-center justify-center"
              onClick={(e) => { e.stopPropagation(); setLightboxIdx(lightboxIdx - 1); }}
            >
              <ChevronLeft className="w-6 h-6" />
            </button>
          )}

          {/* 右箭头 */}
          {lightboxIdx < images.length - 1 && (
            <button
              className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-white/20 hover:bg-white/30 text-white flex items-center justify-center"
              onClick={(e) => { e.stopPropagation(); setLightboxIdx(lightboxIdx + 1); }}
            >
              <ChevronRight className="w-6 h-6" />
            </button>
          )}

          {/* 计数 */}
          <div className="absolute bottom-5 left-1/2 -translate-x-1/2 bg-black/50 text-white text-xs px-3 py-1 rounded-full">
            {lightboxIdx + 1} / {images.length}
          </div>
        </div>
      )}

      <PublishDialog
        open={showPublishDialog}
        onOpenChange={setShowPublishDialog}
        initialTitle={title}
        initialContent={content}
        initialImages={images.map((img) => img.url)}
        onSuccess={() => {
          setSuccess(t("已提交发布任务！"));
          setShowPublishDialog(false);
        }}
      />
    </div>
  );
}
