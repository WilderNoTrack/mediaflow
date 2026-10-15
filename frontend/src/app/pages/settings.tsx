import { Link } from "react-router";
import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { 
  User, 
  Bell, 
  Lock, 
  CreditCard, 
  Globe, 
  Moon,
  Save,
  Upload,
  Loader2
} from "lucide-react";
import { t } from "../../i18n";

// 使用环境变量配置 API 地址，支持 VITE_API_BASE 环境变量
const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

interface Subscription {
  plan: string;
  status: string;
  trial_end: string | null;
  expires_at: string | null;
}

const PLAN_LABELS: Record<string, string> = {
  basic: "基础版",
  pro: "专业版",
  enterprise: "企业版",
};

const STATUS_LABELS: Record<string, string> = {
  trial: "试用期",
  active: "已订阅",
  expired: "已过期",
};

export function SettingsPage() {
  const [userData, setUserData] = useState({
    nickname: "",
    email: "",
    phone: "",
    avatar: "",
    bio: "",
  });
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [notificationSettings, setNotificationSettings] = useState({
    publishSuccess: true,
    dataReport: true,
    systemUpdate: false,
  });
  const [appearanceSettings, setAppearanceSettings] = useState({
    darkMode: false,
    language: "zh-CN",
  });
  const [passwordData, setPasswordData] = useState({
    oldPassword: "",
    newPassword: "",
    confirmPassword: ""
  });
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  // 从 localStorage 读取用户数据和外观设置
  useEffect(() => {
    const storedUser = localStorage.getItem("user");
    const storedToken = localStorage.getItem("token");
    const storedAppearance = localStorage.getItem("appearance");
    
    if (storedUser) {
      const user = JSON.parse(storedUser);
      setUserData(prev => ({
        ...prev,
        nickname: user.nickname || "",
        email: user.email || "",
        phone: user.phone || "",
        bio: user.bio || "",
      }));
    }
    
    // 读取外观设置
    if (storedAppearance) {
      const appearance = JSON.parse(storedAppearance);
      setAppearanceSettings(prev => ({
        ...prev,
        darkMode: appearance.darkMode || false,
        language: appearance.language || "zh-CN",
      }));
      // 应用深色模式
      if (appearance.darkMode) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    
    // 获取完整用户信息
    if (storedToken) {
      fetchUserProfile(storedToken);
    }
  }, []);

  // 从 API 获取用户完整信息
  const fetchUserProfile = async (token: string) => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/user/profile`, {
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        setUserData(prev => ({
          ...prev,
          nickname: data.nickname || prev.nickname,
          email: data.email || prev.email,
          phone: data.phone || prev.phone,
          avatar: data.avatar_url || "",
          bio: data.bio || "",
        }));
        if (data.subscription) setSubscription(data.subscription);
        if (data.notification_settings) setNotificationSettings(data.notification_settings);
      }
    } catch (err) {
      console.error("[设置] 获取用户信息失败:", err);
    } finally {
      setIsLoading(false);
    }
  };

  // 处理表单输入变化
  const handleUserInfoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { id, value } = e.target;
    setUserData(prev => ({
      ...prev,
      [id]: value,
    }));
  };

  // 处理通知设置变化
  const handleNotificationChange = (setting: keyof typeof notificationSettings, value: boolean) => {
    setNotificationSettings(prev => ({
      ...prev,
      [setting]: value,
    }));
  };

  // 处理外观设置变化
  const handleAppearanceChange = (setting: keyof typeof appearanceSettings, value: any) => {
    setAppearanceSettings(prev => ({
      ...prev,
      [setting]: value,
    }));
    // 保存到 localStorage
    localStorage.setItem("appearance", JSON.stringify({
      ...appearanceSettings,
      [setting]: value,
    }));
    // 应用深色模式
    if (setting === "darkMode") {
      if (value) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    }
    // 应用语言设置
    if (setting === "language") {
      localStorage.setItem("language", value);
      window.location.reload();
    }
  };

  // 处理头像上传
  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // 验证文件大小（最大 2MB）
    if (file.size > 2 * 1024 * 1024) {
      setError("图片大小不能超过 2MB");
      return;
    }
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("未登录");
      }
      
      const response = await fetch(`${API_BASE}/api/user/avatar`, {
        method: "POST",
        headers: { 
          "Authorization": `Bearer ${token}` 
        },
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error("上传头像失败");
      }
      
      const data = await response.json();
      setUserData(prev => ({ ...prev, avatar: data.avatar_url }));
      
      // 更新 localStorage 中的用户信息
      const storedUser = JSON.parse(localStorage.getItem("user") || "{}");
      localStorage.setItem("user", JSON.stringify({
        ...storedUser,
        avatar: data.avatar_url,
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传头像失败");
    }
  };

  // 处理密码修改
  const handleChangePassword = async () => {
    setError("");
    
    // 验证密码
    if (passwordData.newPassword.length < 8) {
      setError("密码长度至少为 8 位");
      return;
    }
    
    if (passwordData.newPassword !== passwordData.confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    
    if (!passwordData.oldPassword) {
      setError("请输入旧密码");
      return;
    }
    
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("未登录");
      }
      
      const response = await fetch(`${API_BASE}/api/user/change-password`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          old_password: passwordData.oldPassword,
          new_password: passwordData.newPassword,
        }),
      });
      
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "修改密码失败");
      }
      
      // 清空密码字段
      setPasswordData({
        oldPassword: "",
        newPassword: "",
        confirmPassword: ""
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "修改密码失败");
    }
  };

  // 处理导出数据
  const handleExportData = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("未登录");
      }
      
      const response = await fetch(`${API_BASE}/api/user/export-data`, {
        headers: { 
          "Authorization": `Bearer ${token}` 
        },
      });
      
      if (!response.ok) {
        throw new Error("导出数据失败");
      }
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "mediaflow-export.zip";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导出数据失败");
    }
  };

  // 保存更改
  const handleSave = async () => {
    setIsSaving(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("未登录");
      }

      // 更新用户信息
      const response = await fetch(`${API_BASE}/api/user/profile`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(userData),
      });

      if (!response.ok) {
        throw new Error("更新用户信息失败");
      }

      // 更新 localStorage 中的用户信息
      const updatedUser = await response.json();
      const storedUser = JSON.parse(localStorage.getItem("user") || "{}");
      localStorage.setItem("user", JSON.stringify({
        ...storedUser,
        ...updatedUser,
      }));

      // 保存通知设置
      await fetch(`${API_BASE}/api/user/notifications`, {
        method: "PUT",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(notificationSettings),
      });

      // 显示成功消息
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  // 处理退出登录
  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    window.location.href = "/auth";
  };

  // 处理删除账户
  const handleDeleteAccount = () => {
    setShowDeleteDialog(true);
    setDeletePassword("");
  };

  // 确认删除账户
  const handleConfirmDelete = async () => {
    if (!deletePassword) {
      setError("请输入密码确认删除");
      return;
    }

    setIsDeleting(true);
    setError("");
    try {
      const token = localStorage.getItem("token");
      if (!token) {
        throw new Error("未登录");
      }

      const response = await fetch(`${API_BASE}/api/user/account`, {
        method: "DELETE",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          password: deletePassword,
        }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || "删除失败");
      }

      // 删除成功后清除本地存储并跳转
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/auth";
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="min-h-screen bg-muted">
      {/* Header */}
      <header className="bg-card border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-4">
              <Link to="/accounts">
                <Button variant="ghost" size="sm">
                  ← {t("返回")}
                </Button>
              </Link>
              <h1 className="text-2xl font-bold text-gray-900">{t("设置")}</h1>
            </div>
            <Button 
              onClick={handleSave}
              disabled={isSaving || isLoading}
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t("保存中...")}
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  {t("保存更改")}
                </>
              )}
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Error Message */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-lg">
            {error}
          </div>
        )}

        {/* Account Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <User className="w-5 h-5 mr-2" />
              {t("账户设置")}
            </CardTitle>
            <CardDescription>{t("管理你的个人信息和账户安全")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 头像上传 */}
            <div className="space-y-3">
              <Label>{t("头像")}</Label>
              <div className="flex items-center space-x-4">
                <div className="w-16 h-16 bg-gray-200 rounded-full overflow-hidden">
                  {userData.avatar ? (
                    <img 
                      src={userData.avatar} 
                      alt={t("头像")} 
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-gray-500">
                      <User className="w-8 h-8" />
                    </div>
                  )}
                </div>
                <div>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAvatarChange}
                    className="hidden"
                    id="avatar-upload"
                  />
                  <Button 
                    variant="outline" 
                    size="sm"
                    onClick={() => document.getElementById("avatar-upload")?.click()}
                  >
                    <Upload className="w-4 h-4 mr-2" />
                    {t("更换头像")}
                  </Button>
                  <p className="text-xs text-gray-500 mt-1">{t("支持 JPG、PNG、GIF 格式，最大 2MB")}</p>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="nickname">{t("昵称")}</Label>
                <Input 
                  id="nickname" 
                  value={userData.nickname}
                  onChange={handleUserInfoChange}
                  disabled={isLoading}
                />
              </div>
              <div>
                <Label htmlFor="email">{t("邮箱")}</Label>
                <Input 
                  id="email" 
                  value={userData.email}
                  onChange={handleUserInfoChange}
                  type="email"
                  disabled={isLoading}
                />
              </div>
            </div>
            <div>
              <Label htmlFor="phone">{t("手机号")}</Label>
              <Input 
                id="phone" 
                value={userData.phone}
                onChange={handleUserInfoChange}
                placeholder={t("请输入手机号")} 
                type="tel"
                disabled={isLoading}
              />
            </div>
            <div>
              <Label htmlFor="bio">{t("个人简介")}</Label>
              <textarea 
                id="bio" 
                value={userData.bio}
                onChange={handleUserInfoChange}
                placeholder={t("介绍一下自己...")} 
                className="w-full border rounded-md px-3 py-2 text-sm min-h-[100px] resize-y"
                disabled={isLoading}
              />
            </div>
          </CardContent>
        </Card>

        {/* Notification Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Bell className="w-5 h-5 mr-2" />
              {t("通知设置")}
            </CardTitle>
            <CardDescription>{t("管理你的通知偏好")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("发布成功通知")}</div>
                <div className="text-sm text-gray-500">{t("内容发布成功后发送通知")}</div>
              </div>
              <Switch 
                checked={notificationSettings.publishSuccess}
                onCheckedChange={(checked) => handleNotificationChange("publishSuccess", checked)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("数据报告通知")}</div>
                <div className="text-sm text-gray-500">{t("每周发送数据报告到邮箱")}</div>
              </div>
              <Switch 
                checked={notificationSettings.dataReport}
                onCheckedChange={(checked) => handleNotificationChange("dataReport", checked)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("系统更新通知")}</div>
                <div className="text-sm text-gray-500">{t("接收产品更新和功能通知")}</div>
              </div>
              <Switch 
                checked={notificationSettings.systemUpdate}
                onCheckedChange={(checked) => handleNotificationChange("systemUpdate", checked)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Subscription Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <CreditCard className="w-5 h-5 mr-2" />
              {t("订阅管理")}
            </CardTitle>
            <CardDescription>{t("管理你的订阅方案和支付方式")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {subscription ? (
                <div className={`p-4 rounded-lg ${subscription.status === "active" ? "bg-blue-50" : subscription.status === "trial" ? "bg-green-50" : "bg-gray-50"}`}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <div className={`font-medium ${subscription.status === "active" ? "text-blue-900" : subscription.status === "trial" ? "text-green-900" : "text-gray-900"}`}>
                        当前方案：{PLAN_LABELS[subscription.plan] || subscription.plan}
                        <span className="ml-2 text-sm font-normal">({STATUS_LABELS[subscription.status] || subscription.status})</span>
                      </div>
                      {subscription.status === "trial" && subscription.trial_end && (
                        <div className="text-sm text-green-700">
                          试用截止：{new Date(subscription.trial_end).toLocaleDateString("zh-CN")}
                        </div>
                      )}
                      {subscription.status === "active" && subscription.expires_at && (
                        <div className="text-sm text-blue-700">
                          到期时间：{new Date(subscription.expires_at).toLocaleDateString("zh-CN")}
                        </div>
                      )}
                      {subscription.status === "expired" && (
                        <div className="text-sm text-red-600">订阅已过期，请续费</div>
                      )}
                    </div>
                    <Button variant="outline" size="sm">
                      {subscription.status === "expired" ? t("续费") : t("升级方案")}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-gray-50 rounded-lg text-sm text-gray-500">
                  暂无订阅信息
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Privacy Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Lock className="w-5 h-5 mr-2" />
              {t("隐私设置")}
            </CardTitle>
            <CardDescription>{t("管理你的隐私和数据")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("双因素认证")}</div>
                <div className="text-sm text-gray-500">{t("增强账户安全性")}</div>
              </div>
              <Button variant="outline" size="sm">
                {t("启用")}
              </Button>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("下载个人数据")}</div>
                <div className="text-sm text-gray-500">{t("导出你的所有数据")}</div>
              </div>
              <Button 
                variant="outline" 
                size="sm"
                onClick={handleExportData}
              >
                <Download className="w-4 h-4 mr-2" />
                {t("导出")}
              </Button>
            </div>
            <div className="pt-4 border-t">
              <Button variant="destructive" className="w-full" onClick={handleDeleteAccount}>
                {t("删除账户")}
              </Button>
              <p className="text-xs text-gray-500 mt-2">
                {t("账户删除后，所有数据将无法恢复，请谨慎操作")}
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Password Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Lock className="w-5 h-5 mr-2" />
              {t("密码设置")}
            </CardTitle>
            <CardDescription>{t("更改你的登录密码")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <Label htmlFor="old-password">{t("旧密码")}</Label>
              <Input 
                id="old-password" 
                type="password" 
                placeholder={t("请输入旧密码")}
                value={passwordData.oldPassword}
                onChange={(e) => setPasswordData(prev => ({ ...prev, oldPassword: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="new-password">{t("新密码")}</Label>
              <Input 
                id="new-password" 
                type="password" 
                placeholder={t("至少 8 位字符")}
                value={passwordData.newPassword}
                onChange={(e) => setPasswordData(prev => ({ ...prev, newPassword: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="confirm-password">{t("确认新密码")}</Label>
              <Input 
                id="confirm-password" 
                type="password" 
                placeholder={t("请再次输入新密码")}
                value={passwordData.confirmPassword}
                onChange={(e) => setPasswordData(prev => ({ ...prev, confirmPassword: e.target.value }))}
              />
            </div>
            <Button 
              variant="outline"
              onClick={handleChangePassword}
            >
              {t("更改密码")}
            </Button>
          </CardContent>
        </Card>

        {/* Appearance Settings */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center">
              <Moon className="w-5 h-5 mr-2" />
              {t("外观设置")}
            </CardTitle>
            <CardDescription>{t("自定义你的界面外观")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("深色模式")}</div>
                <div className="text-sm text-gray-500">{t("切换深色/浅色主题")}</div>
              </div>
              <Switch 
                checked={appearanceSettings.darkMode}
                onCheckedChange={(checked) => handleAppearanceChange("darkMode", checked)}
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">{t("语言")}</div>
                <div className="text-sm text-gray-500">{t("选择界面语言")}</div>
              </div>
              <select 
                className="border rounded-md px-3 py-2 text-sm"
                value={appearanceSettings.language}
                onChange={(e) => handleAppearanceChange("language", e.target.value)}
              >
                <option value="zh-CN">{t("简体中文")}</option>
                <option value="en-US">{t("English")}</option>
              </select>
            </div>
          </CardContent>
        </Card>

        {/* Logout Button */}
        <div className="mt-8">
          <Button variant="outline" className="w-full" onClick={handleLogout}>
            {t("退出登录")}
          </Button>
        </div>
      </main>


      {showDeleteDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-medium mb-4">{t("确认删除账户")}</h3>
            <p className="text-gray-600 mb-6">
              {t("此操作将永久删除您的账户和所有数据，且无法恢复。请输入密码确认您的操作。")}
            </p>
            <div className="space-y-4">
              <div>
                <Label htmlFor="delete-password">{t("密码")}</Label>
                <Input
                  id="delete-password"
                  type="password"
                  placeholder={t("请输入密码")}
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                />
              </div>
              <div className="flex space-x-3">
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => setShowDeleteDialog(false)}
                  disabled={isDeleting}
                >
                  {t("取消")}
                </Button>
                <Button
                  variant="destructive"
                  className="flex-1"
                  onClick={handleConfirmDelete}
                  disabled={isDeleting || !deletePassword}
                >
                  {isDeleting ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      {t("删除中...")}
                    </>
                  ) : (
                    t("确认删除")
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

function Download(props: any) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" x2="12" y1="15" y2="3" />
    </svg>
  );
}
