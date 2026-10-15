import { createBrowserRouter, Navigate } from "react-router";
import { LandingPage } from "./pages/landing";
import { AuthPage } from "./pages/auth";
import { ForgotPasswordPage } from "./pages/forgot-password";
import { SettingsPage } from "./pages/settings";
import { PreviewPage } from "./pages/preview";
import { CreatePage } from "./pages/create";
import { AccountsPage } from "./pages/accounts";
import { AccountWorkspacePage } from "./pages/account-workspace";
import { AuthGuard, GuestGuard } from "./components/AuthGuard";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: LandingPage,
  },
  {
    path: "/auth",
    Component: () => (
      <GuestGuard>
        <AuthPage />
      </GuestGuard>
    ),
  },
  {
    path: "/forgot-password",
    Component: () => (
      <GuestGuard>
        <ForgotPasswordPage />
      </GuestGuard>
    ),
  },
  // ─── 账号孵化中台（主流程） ──────────────────────────
  {
    path: "/accounts",
    Component: () => (
      <AuthGuard>
        <AccountsPage />
      </AuthGuard>
    ),
  },
  {
    path: "/accounts/:accountId",
    Component: () => (
      <AuthGuard>
        <AccountWorkspacePage />
      </AuthGuard>
    ),
  },
  // ─── 内容编辑 / 预览 ─────────────────────────────────
  {
    path: "/create",
    Component: () => (
      <AuthGuard>
        <CreatePage />
      </AuthGuard>
    ),
  },
  {
    path: "/preview",
    Component: () => (
      <AuthGuard>
        <PreviewPage />
      </AuthGuard>
    ),
  },
  {
    path: "/settings",
    Component: () => (
      <AuthGuard>
        <SettingsPage />
      </AuthGuard>
    ),
  },
  // ─── 旧路径重定向（向后兼容书签） ─────────────────────
  { path: "/contents", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/chat", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/dashboard", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/dashboard/contents", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/dashboard/create", Component: () => <Navigate to="/create" replace /> },
  { path: "/dashboard/settings", Component: () => <Navigate to="/settings" replace /> },
  { path: "/dashboard/chat", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/onboarding", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/preferences", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/report", Component: () => <Navigate to="/accounts" replace /> },
  { path: "/dashboard/analytics", Component: () => <Navigate to="/accounts" replace /> },
]);
