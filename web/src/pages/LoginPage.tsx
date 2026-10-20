import { useState } from "react";
import { useLogin } from "../api/hooks";
import { Button, ErrorText, Input, Label, Logo } from "../components/ui";

/** 在线版登录。不开放注册：账号由管理员在「成员管理」里开。 */
export function LoginPage() {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-slate-50 via-white to-indigo-50 p-4">
      <form className="w-full max-w-sm space-y-5 rounded-2xl border-2 bg-card p-6 shadow-xl shadow-indigo-500/5"
        onSubmit={(e) => { e.preventDefault(); if (username.trim() && password) login.mutate({ username: username.trim(), password }); }}>
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-lg font-bold text-transparent">媒力 MediaFlow</div>
            <div className="text-xs text-muted-foreground">AI 帮你做小红书</div>
          </div>
        </div>
        <div className="space-y-3">
          <div><Label>用户名</Label><Input autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} /></div>
          <div><Label>密码</Label><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
        </div>
        <ErrorText error={login.error} />
        <Button type="submit" variant="gradient" className="w-full" loading={login.isPending} disabled={!username.trim() || !password}>登录</Button>
        <p className="text-center text-xs text-muted-foreground">还没有账号？找管理员给你开一个</p>
      </form>
    </div>
  );
}
