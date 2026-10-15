import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Checkbox } from "../components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Sparkles, ArrowRight, Mail, Lock, User, Loader2 } from "lucide-react";
import { t } from "../../i18n";

// 使用环境变量配置 API 地址，支持 VITE_API_BASE 环境变量
// 默认值：http://localhost:8000
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export function AuthPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [loginData, setLoginData] = useState({ email: "", password: "" });
  const [registerData, setRegisterData] = useState({ name: "", email: "", password: "", confirmPassword: "", code: "" });
  const [error, setError] = useState("");
  const [codeSent, setCodeSent] = useState(false);
  const [codeLoading, setCodeLoading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: loginData.email,
          password: loginData.password
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || t("登录失败"));
      }
      
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      navigate("/accounts");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("登录失败"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendCode = async () => {
    if (!registerData.email) {
      setError(t("请先输入邮箱地址"));
      console.error("[SendCode] 邮箱为空");
      return;
    }
    
    setCodeLoading(true);
    setError("");
    
    try {
      const response = await fetch(`${API_BASE}/api/auth/send-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: registerData.email,
          purpose: "register"
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        console.error("[SendCode] 响应错误:", data.detail);
        throw new Error(data.detail || t("发送失败"));
      }
      
      setCodeSent(true);
      // 调试模式：倒计时改为 5 秒
      setCountdown(5);
      
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
    } catch (err) {
      console.error("[SendCode] 捕获异常:", err);
      setError(err instanceof Error ? err.message : t("发送验证码失败"));
    } finally {
      setCodeLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (registerData.password !== registerData.confirmPassword) {
      setError(t("密码不匹配"));
      return;
    }
    if (!registerData.code) {
      setError(t("请输入验证码"));
      return;
    }
    setIsLoading(true);
    setError("");
    
    try {
      const response = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: registerData.email,
          password: registerData.password,
          nickname: registerData.name,
          code: registerData.code
        })
      });
      
      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || t("注册失败"));
      }
      
      localStorage.setItem("token", data.access_token);
      localStorage.setItem("user", JSON.stringify(data.user));
      navigate("/accounts");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("注册失败"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex">
      {/* Left Panel - Form */}
      <div className="flex-1 flex items-center justify-center p-8">
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
            <h1 className="text-3xl font-bold mb-2">{t("欢迎回来")}</h1>
            <p className="text-muted-foreground">{t("登录你的账号，开始 AI 运营之旅")}</p>
          </div>

          <Tabs defaultValue="login" className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-6">
              <TabsTrigger value="login">{t("登录")}</TabsTrigger>
              <TabsTrigger value="register">{t("注册")}</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <Card className="border-2">
                <CardContent className="pt-6">
                  <form onSubmit={handleLogin} className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="email">{t("邮箱")}</Label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="email"
                          type="email"
                          placeholder="your@email.com"
                          className="pl-10"
                          value={loginData.email}
                          onChange={(e) => setLoginData({ ...loginData, email: e.target.value })}
                          autoComplete="email"
                          required
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label htmlFor="password">{t("密码")}</Label>
                        <Link to="/forgot-password" className="text-sm text-indigo-600 hover:underline">
                          {t("忘记密码？")}
                        </Link>
                      </div>
                      <div className="relative">
                        <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="password"
                          type="password"
                          placeholder="••••••••"
                          className="pl-10"
                          value={loginData.password}
                          onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                          autoComplete="current-password"
                          required
                        />
                      </div>
                    </div>
                    {error && (
                      <div className="text-sm text-red-500 bg-red-50 p-2 rounded">{error}</div>
                    )}
                    <div className="flex items-center space-x-2">
                      <Checkbox id="remember" />
                      <label
                        htmlFor="remember"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        {t("记住我")}
                      </label>
                    </div>
                    <Button
                      type="submit"
                      className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {t("登录中...")}
                        </>
                      ) : (
                        <>
                          {t("登录")}
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </>
                      )}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="register">
              <Card className="border-2">
                <CardContent className="pt-6">
                  <form onSubmit={handleRegister} className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="name">{t("昵称")}</Label>
                      <div className="relative">
                        <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="name"
                          placeholder="你的昵称"
                          className="pl-10"
                          value={registerData.name}
                          onChange={(e) => setRegisterData({ ...registerData, name: e.target.value })}
                          autoComplete="name"
                          required
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="register-email">{t("邮箱")}</Label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="register-email"
                          type="email"
                          placeholder="your@email.com"
                          className="pl-10"
                          value={registerData.email}
                          onChange={(e) => setRegisterData({ ...registerData, email: e.target.value })}
                          autoComplete="email"
                          required
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="code">{t("验证码")}</Label>
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                          <Input
                            id="code"
                            type="text"
                            placeholder="6 位验证码"
                            className="pl-10"
                            value={registerData.code}
                            onChange={(e) => setRegisterData({ ...registerData, code: e.target.value })}
                            maxLength={6}
                            required
                          />
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          onClick={handleSendCode}
                          disabled={codeLoading || countdown > 0 || !registerData.email}
                          className="whitespace-nowrap"
                        >
                          {codeLoading ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                              {t("发送中...")}
                            </>
                          ) : countdown > 0 ? (
                            `${countdown}${t("秒后重试")}`
                          ) : (
                            t("获取验证码")
                          )}
                        </Button>
                      </div>
                      {codeSent && (
                        <p className="text-xs text-green-600">✓ {t("验证码已发送，请检查邮箱")}</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="register-password">{t("密码")}</Label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="register-password"
                          type="password"
                          placeholder="至少 8 位"
                          className="pl-10"
                          value={registerData.password}
                          onChange={(e) => setRegisterData({ ...registerData, password: e.target.value })}
                          autoComplete="new-password"
                          required
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="confirm-password">{t("确认密码")}</Label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="confirm-password"
                          type="password"
                          placeholder="再次输入密码"
                          className="pl-10"
                          value={registerData.confirmPassword}
                          onChange={(e) => setRegisterData({ ...registerData, confirmPassword: e.target.value })}
                          autoComplete="new-password"
                          required
                        />
                      </div>
                    </div>
                    {error && (
                      <div className="text-sm text-red-500 bg-red-50 p-2 rounded">{error}</div>
                    )}
                    <div className="flex items-start space-x-2">
                      <Checkbox id="terms" />
                      <label
                        htmlFor="terms"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        {t("我已阅读并同意")} <Link to="/terms" className="text-indigo-600 hover:underline">{t("服务条款")}</Link> {t("和")} <Link to="/privacy" className="text-indigo-600 hover:underline">{t("隐私政策")}</Link>
                      </label>
                    </div>
                    <Button
                      type="submit"
                      className="w-full bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700"
                      disabled={isLoading}
                    >
                      {isLoading ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          {t("注册中...")}
                        </>
                      ) : (
                        <>
                          {t("开始免费试用")}
                          <ArrowRight className="ml-2 h-4 w-4" />
                        </>
                      )}
                    </Button>
                  </form>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          <p className="text-center text-sm text-muted-foreground mt-6">
            🎉 {t("7 天免费试用 · 无需信用卡 · 随时取消")}
          </p>
        </div>
      </div>

      {/* Right Panel - Decorative */}
      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-indigo-500 to-purple-600 p-12 items-center justify-center">
        <div className="max-w-lg text-white">
          <div className="mb-8">
              <div className="inline-flex items-center gap-2 bg-white/20 backdrop-blur-sm rounded-full px-4 py-2 text-sm mb-6">
                <Sparkles className="w-4 h-4" />
                {t("AI 驱动的自媒体运营")}
              </div>
              <h2 className="text-4xl font-bold mb-4">
                {t("让 AI 成为你的专属运营官")}
              </h2>
              <p className="text-lg opacity-90">
                {t("设定一次，持续运转。全自动内容创作与发布，让你的小红书账号自动增长。")}
              </p>
          </div>

          <div className="space-y-4">
            {[
              t("24/7 AI 自动运营"),
              t("智能内容生成"),
              t("精准数据分析"),
              t("多账号管理")
            ].map((feature, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-6 h-6 bg-white/20 rounded-full flex items-center justify-center text-sm">✓</div>
                <span className="text-lg">{feature}</span>
              </div>
            ))}
          </div>

          <div className="mt-12 pt-8 border-t border-white/20">
            <p className="text-sm opacity-75">{t("已有超过 1,000+ 位创作者在使用")}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
