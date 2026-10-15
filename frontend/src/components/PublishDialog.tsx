import { useState, useRef, useCallback, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import { X, Loader2, Upload, Image as ImageIcon, AlertCircle } from "lucide-react";
import { AccountSelector, Account } from "./AccountSelector";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface PublishDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialTitle?: string;
  initialContent?: string;
  initialImages?: string[];
  onSuccess?: (taskId: string) => void;
}

interface UploadedImage {
  file: File;
  url: string;
  previewUrl: string;
}

export function PublishDialog({
  open,
  onOpenChange,
  initialTitle = "",
  initialContent = "",
  initialImages = [],
  onSuccess,
}: PublishDialogProps) {
  const [title, setTitle] = useState(initialTitle);
  const [content, setContent] = useState(initialContent);
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  const [isPublishing, setIsPublishing] = useState(false);
  const [error, setError] = useState("");
  const [uploadedImages, setUploadedImages] = useState<UploadedImage[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // Account selection state
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(false);
  const [accountError, setAccountError] = useState("");

  // Cleanup blob URLs when dialog closes
  useEffect(() => {
    if (!open) {
      uploadedImages.forEach((img) => {
        if (img.previewUrl.startsWith("blob:")) {
          URL.revokeObjectURL(img.previewUrl);
        }
      });
      setUploadedImages([]);
    }
  }, [open]);

  // Fetch accounts when dialog opens
  useEffect(() => {
    if (open) {
      fetchAccounts();
    }
  }, [open]);

  const fetchAccounts = async () => {
    setIsLoadingAccounts(true);
    setAccountError("");
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_BASE}/api/xiaohongshu/accounts`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error("获取账号列表失败");
      }

      const data = await response.json();
      if (data.success && Array.isArray(data.accounts)) {
        setAccounts(data.accounts);
        
        // Default to the default account if available
        const defaultAccount = data.accounts.find((acc: Account) => acc.is_default);
        if (defaultAccount) {
          setSelectedAccountId(defaultAccount.id);
        } else if (data.accounts.length > 0) {
          setSelectedAccountId(data.accounts[0].id);
        }
      } else {
        setAccounts([]);
      }
    } catch (err) {
      setAccountError(err instanceof Error ? err.message : "获取账号列表失败");
      setAccounts([]);
    } finally {
      setIsLoadingAccounts(false);
    }
  };

  const handleAddTag = () => {
    if (tagInput.trim() && !tags.includes(tagInput.trim())) {
      setTags([...tags, tagInput.trim()]);
      setTagInput("");
    }
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((tag) => tag !== tagToRemove));
  };

  const uploadImages = async (files: File[]): Promise<string[]> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("images", file);
    });

    const token = localStorage.getItem("token");
    const response = await fetch(`${API_BASE}/api/upload/images`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      throw new Error("图片上传失败");
    }

    const data = await response.json();
    if (!data.success) {
      throw new Error(data.message || "图片上传失败");
    }

    return data.images;
  };

  const handleFiles = async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const validFiles = fileArray.filter((file) =>
      file.type.startsWith("image/") &&
      ["image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"].includes(file.type)
    );

    if (validFiles.length === 0) {
      setError("请选择有效的图片文件 (jpg, jpeg, png, gif, webp)");
      return;
    }

    setIsUploading(true);
    setError("");

    try {
      const uploadedUrls = await uploadImages(validFiles);
      
      const newImages: UploadedImage[] = await Promise.all(
        validFiles.map(async (file, index) => ({
          file,
          url: uploadedUrls[index],
          previewUrl: URL.createObjectURL(file),
        }))
      );

      setUploadedImages((prev) => [...prev, ...newImages]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "图片上传失败");
    } finally {
      setIsUploading(false);
    }
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      await handleFiles(files);
    }
  }, []);

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      await handleFiles(files);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveImage = (index: number) => {
    setUploadedImages((prev) => {
      const removed = prev[index];
      if (removed.previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  const handlePublish = async () => {
    if (!title.trim()) {
      setError("请输入标题");
      return;
    }
    if (title.length > 20) {
      setError("标题最多 20 个字符");
      return;
    }
    if (uploadedImages.length === 0) {
      setError("请至少上传一张图片");
      return;
    }
    if (!selectedAccountId) {
      setError("请选择要发布的账号");
      return;
    }

    setIsPublishing(true);
    setError("");

    try {
      const token = localStorage.getItem("token");
      const imageUrls = uploadedImages.map((img) => img.url);
      const response = await fetch(`${API_BASE}/api/publish/xiaohongshu`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          title,
          content,
          images: imageUrls,
          tags,
          account_id: selectedAccountId,
        }),
      });

      const data = await response.json();

      if (data.success) {
        onSuccess?.(data.task_id);
        onOpenChange(false);
      } else {
        setError(data.message || "发布失败");
      }
    } catch (err) {
      setError("网络错误，请检查 MCP 服务是否启动");
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>发布到小红书</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Account Selector */}
          <div className="space-y-2">
            <Label>
              发布账号
              {isLoadingAccounts && (
                <Loader2 className="w-3 h-3 ml-1 inline animate-spin" />
              )}
            </Label>
            <AccountSelector
              accounts={accounts}
              selectedAccountId={selectedAccountId}
              onSelect={setSelectedAccountId}
              disabled={isLoadingAccounts || isPublishing}
              placeholder="选择发布账号..."
              emptyMessage="暂无账号，请先添加账号"
            />
            {accountError && (
              <div className="flex items-center gap-1 text-sm text-destructive">
                <AlertCircle className="w-3 h-3" />
                <span>{accountError}</span>
              </div>
            )}
            {accounts.length === 0 && !isLoadingAccounts && !accountError && (
              <p className="text-sm text-muted-foreground">
                您还没有添加任何账号，请先在小红书账号管理中添加账号
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label>标题 ({title.length}/20)</Label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value.slice(0, 20))}
              placeholder="输入笔记标题..."
            />
          </div>

          <div className="space-y-2">
            <Label>正文内容</Label>
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="输入正文内容..."
              rows={5}
            />
          </div>

          <div className="space-y-2">
            <Label>图片 (至少 1 张)</Label>
            <div
              className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                isDragOver
                  ? "border-primary bg-primary/5"
                  : "border-input hover:border-primary/50"
              }`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="flex flex-col items-center gap-2">
                <ImageIcon className={`w-8 h-8 ${isDragOver ? "text-primary" : "text-muted-foreground"}`} />
                <div className="text-sm text-muted-foreground">
                  {isDragOver ? (
                    <span>松开以上传图片</span>
                  ) : (
                    <span>拖拽图片到此处，或点击选择文件</span>
                  )}
                </div>
                <Input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/jpg,image/png,image/gif,image/webp"
                  multiple
                  className="hidden"
                  onChange={handleFileSelect}
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      上传中...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      选择图片
                    </>
                  )}
                </Button>
              </div>
            </div>

            {uploadedImages.length > 0 && (
              <div className="grid grid-cols-4 gap-2 mt-2">
                {uploadedImages.map((image, index) => (
                  <div
                    key={index}
                    className="relative aspect-square rounded-lg overflow-hidden border bg-muted group"
                  >
                    <img
                      src={image.previewUrl}
                      alt={`Uploaded ${index}`}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveImage(index)}
                      className="absolute top-1 right-1 p-1 rounded-full bg-destructive text-destructive-foreground opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive/90"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label>话题标签</Label>
            <div className="flex gap-2">
              <Input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                placeholder="输入标签..."
                onKeyDown={(e) => e.key === "Enter" && handleAddTag()}
              />
              <Button onClick={handleAddTag} variant="outline">
                添加
              </Button>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="gap-1">
                  #{tag}
                  <X
                    className="w-3 h-3 cursor-pointer"
                    onClick={() => handleRemoveTag(tag)}
                  />
                </Badge>
              ))}
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handlePublish} disabled={isPublishing}>
            {isPublishing ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                发布中...
              </>
            ) : (
              "发布"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
