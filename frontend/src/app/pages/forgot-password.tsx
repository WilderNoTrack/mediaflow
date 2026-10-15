import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Mail, Lock, ArrowLeft, Loader2, CheckCircle } from "lucide-react";

const API_BASE = "http://localhost:8000";

export function ForgotPasswordPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  const handleSendCode = async () => {
    if (!email) {
      setError("请输入邮箱地址");
      return;
    }
    
    setCodeLoading(true);
    setError("");
    
    try {
      const response = await fetch(`${API_BASE}/api/auth/send-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
          purpose: "reset_password"
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || "发送失败");
      }
      
      setCountdown(60);
      
      // Start countdown
      const timer = setInterval(() => {
        setCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(timer);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      
      // Move to step 2
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送验证码失败");
    } finally {
      setCodeLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (newPassword !== confirmPassword) {
      setError("密码不匹配");
      return;
    }
    
    if (newPassword.length < 8) {
      setError("密码至少需要 8 位");
      return;
    }
    
    setIsLoading(true);
    setError("");
    
    try {
      const response = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email,
          code: code,
          new_password: newPassword
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || "重置失败");
      }
      
      setSuccess(true);
      
      // Redirect to login after 2 seconds
      setTimeout(() => {
        navigate("/auth");
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置密码失败");
    } finally {
      setIsLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
        <Card className="w-full max-w-md border-2">
          <CardContent className="pt-6">
            <div className="text-center">
              <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
              <h2 className="text-2xl font-bold mb-2">密码重置成功</h2>
              <p className="text-muted-foreground mb-6">
                您的密码已成功重置，即将跳转到登录页面...
              </p>
              <Button
                onClick={() => navigate("/auth")}
                className="bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
              >
                立即登录
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2 mb-8">
          <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-2xl shadow-lg shadow-indigo-200">
            🌀
          </div>
          <div>
            <div className="font-bold text-lg bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">媒力</div>
            <div className="text-xs text-muted-foreground">MediaFlow</div>
          </div>
        </Link>

        <div className="mb-8">
          <div className="flex items-center gap-2 mb-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/auth")}
              className="p-0 h-auto"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              返回登录
            </Button>
          </div>
          <h1 className="text-3xl font-bold mb-2">忘记密码</h1>
          <p className="text-muted-foreground">
            {step === 1 ? "输入邮箱，我们将发送验证码给您" : "输入验证码和新密码"}
          </p>
        </div>

        {/* Progress Indicator */}
        <div className="flex items-center gap-2 mb-6">
          <div className={`flex-1 h-2 rounded-full ${step >= 1 ? "bg-indigo-500" : "bg-gray-200"}`} />
          <div className={`flex-1 h-2 rounded-full ${step >= 2 ? "bg-indigo-500" : "bg-gray-200"}`} />
        </div>

        <Card className="border-2">
          <CardHeader>
            <CardTitle>{step === 1 ? "验证邮箱" : "重置密码"}</CardTitle>
            <CardDescription>
              {step === 1 ? "请输入您的注册邮箱" : "请输入验证码和新密码"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {step === 1 ? (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">邮箱</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="your@email.com"
                      className="pl-10"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="email"
                      required
                    />
                  </div>
                </div>
                {error && (
                  <div className="text-sm text-red-500 bg-red-50 p-2 rounded">{error}</div>
                )}
                <Button
                  onClick={handleSendCode}
                  className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                  disabled={codeLoading || !email}
                >
                  {codeLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      发送中...
                    </>
                  ) : (
                    "发送验证码"
                  )}
                </Button>
              </div>
            ) : (
              <form onSubmit={handleResetPassword} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="code">验证码</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="code"
                      type="text"
                      placeholder="6 位验证码"
                      className="pl-10"
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      maxLength={6}
                      required
                    />
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">已发送到：{email}</span>
                    <Button
                      type="button"
                      variant="link"
                      onClick={handleSendCode}
                      disabled={countdown > 0}
                      className="h-auto p-0"
                    >
                      {countdown > 0 ? `${countdown}秒后重发` : "重新发送"}
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="new-password">新密码</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="new-password"
                      type="password"
                      placeholder="至少 8 位"
                      className="pl-10"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="confirm-password">确认密码</Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="confirm-password"
                      type="password"
                      placeholder="再次输入新密码"
                      className="pl-10"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </div>
                </div>
                {error && (
                  <div className="text-sm text-red-500 bg-red-50 p-2 rounded">{error}</div>
                )}
                <Button
                  type="submit"
                  className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                  disabled={isLoading || !code || !newPassword || !confirmPassword}
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      重置中...
                    </>
                  ) : (
                    "重置密码"
                  )}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>

        <p className="text-center text-sm text-muted-foreground mt-6">
          记得密码了？{" "}
          <Link to="/auth" className="text-indigo-600 hover:underline">
            返回登录
          </Link>
        </p>
      </div>
    </div>
  );
}
