import { useState, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import {
  ArrowLeft, Edit3, Send, Heart, Star, MessageCircle,
  Share2, AlertCircle, ChevronLeft, ChevronRight, Bookmark,
} from "lucide-react";
import { PublishDialog } from "../../components/PublishDialog";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const resolveImg = (url: string) => url?.startsWith("/") ? `${API_BASE}${url}` : (url || "");

export function PreviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const data = location.state as {
    id?: string;
    title?: string;
    content?: string;
    images?: string[];
    tags?: string[];
  } | null;

  const [showPublish, setShowPublish] = useState(false);
  const [imgIndex, setImgIndex] = useState(0);
  const [imgErrors, setImgErrors] = useState<Set<number>>(new Set());
  const touchStartX = useRef(0);
  const touchEndX = useRef(0);

  if (!data?.title && !data?.content) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
          <p className="text-muted-foreground mb-4">没有内容可以预览</p>
          <Button variant="ghost" className="gap-2" onClick={() => navigate(-1)}>
            <ArrowLeft className="w-4 h-4" />返回
          </Button>
        </div>
      </div>
    );
  }

  const title = data?.title || "";
  const rawContent = data?.content || "";
  const content = rawContent.split("\n").filter((l) => !l.startsWith("标签：")).join("\n");
  // 过滤空 URL，把 placehold.co 占位图标记为 null（用空白框代替）
  const rawImages = data?.images || [];
  const images = rawImages.map((src: string) =>
    src && !src.includes("placehold.co") ? resolveImg(src) : null
  );
  const tags = (data?.tags || []).filter((t) => !t.startsWith("标签："));
  const id = data?.id;

  const prevImg = () => setImgIndex((i) => (i - 1 + images.length) % images.length);
  const nextImg = () => setImgIndex((i) => (i + 1) % images.length);

  const onTouchStart = (e: React.TouchEvent) => { touchStartX.current = e.touches[0].clientX; };
  const onTouchEnd = (e: React.TouchEvent) => {
    touchEndX.current = e.changedTouches[0].clientX;
    const diff = touchStartX.current - touchEndX.current;
    if (Math.abs(diff) > 40) diff > 0 ? nextImg() : prevImg();
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-gray-900">
      {/* ── 顶部操作栏（平台功能） ── */}
      <header className="border-b bg-white dark:bg-gray-950 sticky top-0 z-50 shadow-sm">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" className="gap-2" onClick={() => navigate(-1)}>
              <ArrowLeft className="w-4 h-4" />返回
            </Button>
            <div>
              <h1 className="text-base font-bold">内容预览</h1>
              <p className="text-xs text-muted-foreground">小红书图文效果</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/create", {
                state: { id, title, content: rawContent, tags: data?.tags, images,
                         imagePrompts: (data as any)?.imagePrompts || (data as any)?.image_prompts || [] },
              })}
            >
              <Edit3 className="w-4 h-4 mr-1.5" />编辑
            </Button>
            <Button
              size="sm"
              className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
              onClick={() => setShowPublish(true)}
            >
              <Send className="w-4 h-4 mr-1.5" />发布
            </Button>
          </div>
        </div>
      </header>

      {/* ── 内容区 ── */}
      <div className="flex justify-center py-6 px-4">
        {/* 手机外壳 */}
        <div
          className="w-full bg-white dark:bg-gray-950 shadow-2xl overflow-hidden"
          style={{
            maxWidth: 390,
            borderRadius: "2.5rem",
            border: "3px solid #111827",
          }}
        >
          {/* 状态栏 */}
          <div className="bg-white dark:bg-gray-950 px-6 pt-3 pb-1 flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">9:41</span>
            <div className="w-24 h-5 bg-black rounded-full mx-auto absolute left-1/2 -translate-x-1/2" />
            <div className="flex items-center gap-1">
              <svg className="w-3.5 h-3.5 text-gray-800 dark:text-gray-200" fill="currentColor" viewBox="0 0 24 24">
                <path d="M1.5 8.5a13 13 0 0121 0M5 12a10 10 0 0114 0M8.5 15.5a6 6 0 017 0M12 19h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" fill="none"/>
              </svg>
              <svg className="w-3 h-3 text-gray-800 dark:text-gray-200" fill="currentColor" viewBox="0 0 24 24">
                <rect x="2" y="7" width="15" height="11" rx="2" stroke="currentColor" strokeWidth="2" fill="none"/>
                <path d="M17 11l4-2v8l-4-2" stroke="currentColor" strokeWidth="2" fill="none"/>
              </svg>
            </div>
          </div>

          {/* XHS 导航栏 */}
          <div className="bg-white dark:bg-gray-950 px-4 py-2 flex items-center justify-between border-b border-gray-100 dark:border-gray-800">
            <ChevronLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
            <div className="flex items-center gap-4 text-xs font-medium text-gray-500">
              <span className="text-gray-900 dark:text-white border-b-2 border-rose-500 pb-0.5">图文</span>
            </div>
            <Share2 className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          </div>

          {/* 可滚动内容（无滚动条） */}
          <div
            className="overflow-y-auto"
            style={{ maxHeight: "72vh", scrollbarWidth: "none", msOverflowStyle: "none" }}
          >
            <style>{`
              .xhs-body::-webkit-scrollbar{display:none}
              .animate-fade{animation:fadeIn 0.2s ease-in-out}
              @keyframes fadeIn{from{opacity:0}to{opacity:1}}
            `}</style>

            {/* ── 图片轮播 ── */}
            <div
              className="relative bg-gray-100 select-none"
              style={{ aspectRatio: "3/4" }}
              onTouchStart={onTouchStart}
              onTouchEnd={onTouchEnd}
            >
              {images.length > 0 ? (
                <>
                  {/* 只渲染当前图，切换用淡入淡出 */}
                  <div key={imgIndex} className="w-full h-full animate-fade">
                    {(() => {
                      const src = images[imgIndex];
                      return src && !imgErrors.has(imgIndex) ? (
                        <img
                          src={src}
                          alt={`图${imgIndex + 1}`}
                          className="w-full h-full object-cover"
                          onError={() => setImgErrors(prev => new Set([...prev, imgIndex]))}
                        />
                      ) : (
                        <div className="w-full h-full flex flex-col items-center justify-center gap-3 bg-gray-100">
                          <div className="w-14 h-14 rounded-full bg-gray-200 flex items-center justify-center">
                            <span className="text-2xl">📷</span>
                          </div>
                          <p className="text-sm text-gray-400">第 {imgIndex + 1} 张</p>
                          <p className="text-xs text-gray-300">待生成</p>
                        </div>
                      );
                    })()}
                  </div>

                  {/* 左右箭头（多图时显示） */}
                  {images.length > 1 && (
                    <>
                      <button
                        onClick={prevImg}
                        className="absolute left-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/30 hover:bg-black/50 rounded-full flex items-center justify-center text-white transition-all"
                      >
                        <ChevronLeft className="w-5 h-5" />
                      </button>
                      <button
                        onClick={nextImg}
                        className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-black/30 hover:bg-black/50 rounded-full flex items-center justify-center text-white transition-all"
                      >
                        <ChevronRight className="w-5 h-5" />
                      </button>
                    </>
                  )}

                  {/* 图片计数角标 */}
                  {images.length > 1 && (
                    <div className="absolute top-3 right-3 bg-black/50 text-white text-xs px-2 py-0.5 rounded-full">
                      {imgIndex + 1}/{images.length}
                    </div>
                  )}

                  {/* 底部圆点 */}
                  {images.length > 1 && images.length <= 9 && (
                    <div className="absolute bottom-3 left-0 right-0 flex justify-center gap-1.5">
                      {images.map((_, i) => (
                        <button
                          key={i}
                          onClick={() => setImgIndex(i)}
                          className={`rounded-full transition-all duration-200 ${
                            i === imgIndex ? "w-4 h-1.5 bg-white" : "w-1.5 h-1.5 bg-white/50"
                          }`}
                        />
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center gap-3 bg-gray-50">
                  <div className="w-16 h-16 rounded-full bg-gray-200 flex items-center justify-center">
                    <span className="text-3xl">📷</span>
                  </div>
                  <p className="text-sm text-gray-400">暂无配图</p>
                  <p className="text-xs text-gray-300">在编辑页生成图片</p>
                </div>
              )}
            </div>

            {/* ── 正文区 ── */}
            <div className="bg-white dark:bg-gray-950 px-4 pt-4 pb-2">
              {/* 作者信息 */}
              <div className="flex items-center gap-2.5 mb-3">
                <div className="w-9 h-9 rounded-full bg-gradient-to-br from-rose-400 to-pink-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                  我
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900 dark:text-white leading-none">我的账号</div>
                  <div className="text-xs text-gray-400 mt-0.5">刚刚</div>
                </div>
                <button className="text-xs text-rose-500 border border-rose-400 rounded-full px-3 py-1 font-medium hover:bg-rose-50 transition-colors">
                  关注
                </button>
              </div>

              {/* 标题 */}
              <h2 className="text-[15px] font-bold text-gray-900 dark:text-white leading-snug mb-2">
                {title}
              </h2>

              {/* 正文 */}
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-line">
                {content}
              </p>

              {/* 标签 */}
              {tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {tags.map((tag, i) => (
                    <span key={i} className="text-sm text-blue-500 font-medium hover:underline cursor-pointer">
                      #{tag}
                    </span>
                  ))}
                </div>
              )}

              {/* 位置/话题行 */}
              <div className="flex items-center gap-2 mt-3 text-xs text-gray-400">
                <span>📍 中国大陆</span>
                <span>·</span>
                <span>编辑于手机</span>
              </div>
            </div>

            {/* 分割线 */}
            <div className="h-2 bg-gray-50 dark:bg-gray-900" />

            {/* 评论区占位 */}
            <div className="bg-white dark:bg-gray-950 px-4 py-3">
              <div className="text-xs font-semibold text-gray-500 mb-3">共 0 条评论</div>
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-gray-200 dark:bg-gray-700" />
                <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full px-3 py-1.5 text-xs text-gray-400">
                  说点什么...
                </div>
              </div>
            </div>

            {/* 底部安全区 */}
            <div className="h-16" />
          </div>

          {/* ── 底部互动栏（固定在手机底部） ── */}
          <div className="bg-white dark:bg-gray-950 border-t border-gray-100 dark:border-gray-800 px-4 py-2.5 flex items-center justify-between">
            {/* 搜索框占位 */}
            <div className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full px-3 py-1.5 text-xs text-gray-400 mr-3">
              说点什么...
            </div>
            <div className="flex items-center gap-4">
              <div className="flex flex-col items-center gap-0.5">
                <Heart className="w-5 h-5 text-gray-500" />
                <span className="text-[10px] text-gray-400">赞</span>
              </div>
              <div className="flex flex-col items-center gap-0.5">
                <Bookmark className="w-5 h-5 text-gray-500" />
                <span className="text-[10px] text-gray-400">收藏</span>
              </div>
              <div className="flex flex-col items-center gap-0.5">
                <MessageCircle className="w-5 h-5 text-gray-500" />
                <span className="text-[10px] text-gray-400">评论</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 内容信息卡（手机下方） */}
      <div className="flex justify-center pb-8 px-4">
        <div className="w-full max-w-[390px] bg-white dark:bg-gray-950 rounded-2xl shadow-sm border px-5 py-4 flex items-center justify-between text-sm">
          <div className="text-center">
            <div className="font-semibold text-gray-900 dark:text-white">{content.replace(/\s/g, "").length}</div>
            <div className="text-xs text-gray-400">字数</div>
          </div>
          <div className="w-px h-8 bg-gray-100" />
          <div className="text-center">
            <div className="font-semibold text-gray-900 dark:text-white">{images.length}</div>
            <div className="text-xs text-gray-400">图片</div>
          </div>
          <div className="w-px h-8 bg-gray-100" />
          <div className="text-center">
            <div className="font-semibold text-gray-900 dark:text-white">{tags.length}</div>
            <div className="text-xs text-gray-400">标签</div>
          </div>
          <div className="w-px h-8 bg-gray-100" />
          <Button
            size="sm"
            className="bg-gradient-to-r from-rose-500 to-pink-500 hover:from-rose-600 hover:to-pink-600 text-white border-0"
            onClick={() => setShowPublish(true)}
          >
            <Send className="w-3.5 h-3.5 mr-1.5" />发布
          </Button>
        </div>
      </div>

      <PublishDialog
        open={showPublish}
        onOpenChange={setShowPublish}
        initialTitle={title}
        initialContent={rawContent}
        initialImages={images}
        onSuccess={() => {
          setShowPublish(false);
          navigate(-1);
        }}
      />
    </div>
  );
}
