import { Navigate, useLocation } from "react-router";

/**
 * 开发直通：本地调试时跳过注册/登录界面。
 *
 * 只在 `npm run dev`（import.meta.env.DEV 为 true）且配置了 VITE_DEV_TOKEN 时生效。
 * 生产构建里 DEV 恒为 false，整段会被 Vite 静态移除，不存在被误开启的可能。
 *
 * 注意后端所有 /api/* 都要求有效 JWT，所以这里必须塞一个真实令牌，
 * 只是绕过前端跳转的话页面会全部 401 变空白。
 * 令牌配在 frontend/.env.local（已被 .gitignore 排除）。
 */
const DEV_TOKEN = import.meta.env.DEV ? import.meta.env.VITE_DEV_TOKEN : undefined;

function getToken(): string | null {
  const existing = localStorage.getItem("token");
  if (existing) return existing;
  if (DEV_TOKEN) {
    localStorage.setItem("token", DEV_TOKEN);
    console.info("[dev] 已使用 VITE_DEV_TOKEN 自动登录，跳过登录界面");
    return DEV_TOKEN;
  }
  return null;
}

// 路由保护组件
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const token = getToken();
  const location = useLocation();

  if (!token) {
    // 保存用户想要访问的页面，登录后重定向
    return <Navigate to="/auth" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

// 未登录用户访问的组件保护
export function GuestGuard({ children }: { children: React.ReactNode }) {
  const token = getToken();

  if (token) {
    return <Navigate to="/accounts" replace />;
  }

  return <>{children}</>;
}
