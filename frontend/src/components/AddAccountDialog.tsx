import { useState, useEffect, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Loader2, CheckCircle2, AlertCircle, QrCode, Smartphone } from "lucide-react";

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface AddAccountDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccountAdded?: (account: AccountResponse) => void;
}

interface AccountResponse {
  id: string;
  user_id: string;
  mcp_account_id: string;
  is_default: boolean;
  created_at: string;
}

interface QRCodeResponse {
  success: boolean;
  qrcode_data?: string;
  qrcode_url?: string;
  error?: string;
}

interface StatusResponse {
  success: boolean;
  logged_in: boolean;
  account?: string;
  error?: string;
}

type Step = "name" | "qrcode" | "success" | "error";

export function AddAccountDialog({
  open,
  onOpenChange,
  onAccountAdded,
}: AddAccountDialogProps) {
  const [step, setStep] = useState<Step>("name");
  const [accountName, setAccountName] = useState("");
  const [accountId, setAccountId] = useState<string | null>(null);
  const [qrCodeData, setQrCodeData] = useState<string | null>(null);
  const [qrCodeUrl, setQrCodeUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdAccount, setCreatedAccount] = useState<AccountResponse | null>(null);

  // Reset state when dialog opens
  useEffect(() => {
    if (open) {
      setStep("name");
      setAccountName("");
      setAccountId(null);
      setQrCodeData(null);
      setQrCodeUrl(null);
      setIsLoading(false);
      setError(null);
      setCreatedAccount(null);
    }
  }, [open]);

  const getAuthHeaders = () => {
    const token = localStorage.getItem("token");
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  // Step 1: Create account
  const handleCreateAccount = async () => {
    if (!accountName.trim()) {
      setError("请输入账号名称");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/api/xiaohongshu/accounts`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ name: accountName.trim() }),
      });

      const data: AccountResponse = await response.json();

      if (!response.ok) {
        throw new Error("创建账号失败");
      }

      setCreatedAccount(data);
      setAccountId(data.id);
      setStep("qrcode");

      // Fetch QR code
      await fetchQRCode(data.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建账号失败，请重试");
      setStep("error");
    } finally {
      setIsLoading(false);
    }
  };

  // Step 2: Get QR code
  const fetchQRCode = async (id: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_BASE}/api/xiaohongshu/accounts/${id}/qrcode`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...getAuthHeaders(),
          },
        }
      );

      const data: QRCodeResponse = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "获取二维码失败");
      }

      setQrCodeData(data.qrcode_data || null);
      setQrCodeUrl(data.qrcode_url || null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "获取二维码失败");
      setStep("error");
    } finally {
      setIsLoading(false);
    }
  };

  // Step 3: Poll login status
  const checkLoginStatus = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const response = await fetch(
          `${API_BASE}/api/xiaohongshu/accounts/${id}/status`,
          {
            headers: getAuthHeaders(),
          }
        );

        const data: StatusResponse = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data.error || "检查登录状态失败");
        }

        return data.logged_in;
      } catch (err) {
        console.error("检查登录状态失败:", err);
        return false;
      }
    },
    []
  );

  // Polling effect for login status
  useEffect(() => {
    if (step !== "qrcode" || !accountId) return;

    let pollCount = 0;
    const maxPolls = 150; // 5 minutes (150 * 2 seconds)
    let isCancelled = false;

    const poll = async () => {
      if (isCancelled || pollCount >= maxPolls) {
        if (pollCount >= maxPolls && !isCancelled) {
          setError("二维码已过期，请重试");
          setStep("error");
        }
        return;
      }

      pollCount++;
      const loggedIn = await checkLoginStatus(accountId);

      if (loggedIn) {
        setStep("success");
        if (createdAccount) {
          onAccountAdded?.(createdAccount);
        }
        return;
      }

      // Continue polling
      setTimeout(poll, 2000);
    };

    // Start polling after a short delay
    const timeoutId = setTimeout(poll, 2000);

    return () => {
      isCancelled = true;
      clearTimeout(timeoutId);
    };
  }, [step, accountId, checkLoginStatus, createdAccount, onAccountAdded]);

  const handleClose = () => {
    onOpenChange(false);
  };

  const handleRetry = () => {
    if (step === "error") {
      setStep("name");
      setError(null);
    }
  };

  const renderStepContent = () => {
    switch (step) {
      case "name":
        return (
          <div className="space-y-6 py-4">
            <div className="space-y-2">
              <Label htmlFor="account-name">账号名称</Label>
              <Input
                id="account-name"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                placeholder="输入小红书账号名称"
                disabled={isLoading}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !isLoading) {
                    handleCreateAccount();
                  }
                }}
              />
              <p className="text-xs text-muted-foreground">
                此名称用于在平台内标识您的账号
              </p>
            </div>

            {error && (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="w-4 h-4" />
                <span>{error}</span>
              </div>
            )}
          </div>
        );

      case "qrcode":
        return (
          <div className="space-y-6 py-4">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center gap-2 text-muted-foreground">
                <Smartphone className="w-5 h-5" />
                <span className="text-sm">请使用小红书 App 扫描二维码登录</span>
              </div>

              <div className="relative">
                {isLoading ? (
                  <div className="w-48 h-48 mx-auto flex items-center justify-center bg-muted rounded-lg">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                  </div>
                ) : qrCodeData ? (
                  <div className="relative w-48 h-48 mx-auto">
                    <img
                      src={qrCodeData}
                      alt="Login QR Code"
                      className="w-full h-full object-contain rounded-lg border"
                    />
                    {/* Scanning animation overlay */}
                    <div className="absolute inset-0 overflow-hidden rounded-lg pointer-events-none">
                      <div
                        className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent animate-scan"
                        style={{
                          animation: "scan 2s linear infinite",
                        }}
                      />
                    </div>
                  </div>
                ) : qrCodeUrl ? (
                  <div className="w-48 h-48 mx-auto">
                    <img
                      src={qrCodeUrl}
                      alt="Login QR Code"
                      className="w-full h-full object-contain rounded-lg border"
                    />
                  </div>
                ) : (
                  <div className="w-48 h-48 mx-auto flex items-center justify-center bg-muted rounded-lg">
                    <QrCode className="w-12 h-12 text-muted-foreground" />
                  </div>
                )}
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>等待扫码登录...</span>
                </div>
                <p className="text-xs text-muted-foreground">
                  二维码将在 5 分钟后过期
                </p>
              </div>
            </div>
          </div>
        );

      case "success":
        return (
          <div className="space-y-6 py-8">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center animate-in zoom-in duration-300">
                  <CheckCircle2 className="w-8 h-8 text-green-600" />
                </div>
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-semibold">账号添加成功</h3>
                <p className="text-sm text-muted-foreground">
                  账号 "{accountName}" 已成功绑定到您的账户
                </p>
              </div>
            </div>
          </div>
        );

      case "error":
        return (
          <div className="space-y-6 py-8">
            <div className="text-center space-y-4">
              <div className="flex items-center justify-center">
                <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
                  <AlertCircle className="w-8 h-8 text-destructive" />
                </div>
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-semibold text-destructive">
                  添加失败
                </h3>
                <p className="text-sm text-muted-foreground">
                  {error || "发生未知错误，请重试"}
                </p>
              </div>
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  const renderFooter = () => {
    switch (step) {
      case "name":
        return (
          <DialogFooter>
            <Button variant="outline" onClick={handleClose} disabled={isLoading}>
              取消
            </Button>
            <Button onClick={handleCreateAccount} disabled={isLoading || !accountName.trim()}>
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  处理中...
                </>
              ) : (
                "下一步"
              )}
            </Button>
          </DialogFooter>
        );

      case "qrcode":
        return (
          <DialogFooter>
            <Button variant="outline" onClick={handleClose}>
              取消
            </Button>
          </DialogFooter>
        );

      case "success":
        return (
          <DialogFooter>
            <Button
              onClick={() => {
                handleClose();
              }}
            >
              完成
            </Button>
          </DialogFooter>
        );

      case "error":
        return (
          <DialogFooter>
            <Button variant="outline" onClick={handleClose}>
              取消
            </Button>
            <Button onClick={handleRetry}>重试</Button>
          </DialogFooter>
        );

      default:
        return null;
    }
  };

  const getStepTitle = () => {
    switch (step) {
      case "name":
        return "添加小红书账号";
      case "qrcode":
        return "扫描二维码";
      case "success":
        return "添加成功";
      case "error":
        return "添加失败";
      default:
        return "添加账号";
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {step === "qrcode" && <QrCode className="w-5 h-5" />}
            {getStepTitle()}
          </DialogTitle>
          {step === "name" && (
            <DialogDescription>
              输入账号名称以开始绑定流程
            </DialogDescription>
          )}
        </DialogHeader>

        {renderStepContent()}

        {renderFooter()}
      </DialogContent>

      {/* Add custom animation styles */}
      <style>{`
        @keyframes scan {
          0% {
            top: 0;
            opacity: 0;
          }
          10% {
            opacity: 1;
          }
          90% {
            opacity: 1;
          }
          100% {
            top: 100%;
            opacity: 0;
          }
        }
        
        .animate-scan {
          animation: scan 2s linear infinite;
        }
      `}</style>
    </Dialog>
  );
}
