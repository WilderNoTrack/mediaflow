import { useState } from "react";
import { Button } from "@/app/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/app/components/ui/card";
import { Badge } from "@/app/components/ui/badge";
import { Avatar, AvatarImage, AvatarFallback } from "@/app/components/ui/avatar";
import {
  Plus,
  Star,
  Trash2,
  UserCircle,
  AlertCircle,
  CheckCircle2,
  MoreVertical,
} from "lucide-react";
import { t } from "@/i18n";

export interface XiaohongshuAccount {
  id: string;
  mcp_account_id?: string;
  user_id: string;
  is_default: boolean;
  nickname?: string;
  username?: string;
  avatar_url?: string;
  status?: "connected" | "disconnected" | "expired";
  created_at?: string;
}

export interface AccountManagerCardProps {
  accounts: XiaohongshuAccount[];
  onAddAccount: () => void;
  onSetDefault: (accountId: string) => void;
  onDelete: (accountId: string) => void;
  isLoading?: boolean;
}

export function AccountManagerCard({
  accounts,
  onAddAccount,
  onSetDefault,
  onDelete,
  isLoading = false,
}: AccountManagerCardProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleDelete = (accountId: string) => {
    setDeletingId(accountId);
    onDelete(accountId);
    setTimeout(() => setDeletingId(null), 500);
  };

  const getStatusConfig = (status?: string) => {
    switch (status) {
      case "connected":
        return {
          icon: CheckCircle2,
          label: t("已登录"),
          className: "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800",
        };
      case "expired":
        return {
          icon: AlertCircle,
          label: t("已过期"),
          className: "bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800",
        };
      default:
        return {
          icon: UserCircle,
          label: t("未登录"),
          className: "bg-slate-100 dark:bg-slate-900/30 text-slate-700 dark:text-slate-400 border-slate-200 dark:border-slate-800",
        };
    }
  };

  return (
    <Card className="w-full border-2 hover:shadow-xl transition-all duration-300">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-xl font-semibold">
              {t("小红书账号管理")}
            </CardTitle>
            <CardDescription className="text-sm text-muted-foreground mt-1">
              {t("管理您的多个小红书账号")}
            </CardDescription>
          </div>
          <Button
            onClick={onAddAccount}
            className="gap-2 bg-gradient-to-r from-rose-500 to-red-600 hover:from-rose-600 hover:to-red-700 text-white shadow-md hover:shadow-lg transition-all duration-200"
            size="sm"
          >
            <Plus className="w-4 h-4" />
            {t("添加账号")}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-rose-500" />
          </div>
        ) : accounts.length === 0 ? (
          <div className="text-center py-12 px-4">
            <div className="w-16 h-16 bg-gradient-to-br from-rose-100 to-red-100 dark:from-rose-900/30 dark:to-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
              <UserCircle className="w-8 h-8 text-rose-500" />
            </div>
            <h3 className="text-lg font-medium text-foreground mb-2">
              {t("暂无账号")}
            </h3>
            <p className="text-sm text-muted-foreground mb-4 max-w-xs mx-auto">
              {t("还没有添加小红书账号，点击下方按钮添加您的第一个账号")}
            </p>
            <Button
              onClick={onAddAccount}
              variant="outline"
              className="gap-2 border-rose-200 hover:bg-rose-50 dark:border-rose-800 dark:hover:bg-rose-950"
            >
              <Plus className="w-4 h-4" />
              {t("添加账号")}
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {accounts.map((account, index) => {
              const statusConfig = getStatusConfig(account.status);
              const StatusIcon = statusConfig.icon;
              const isHovered = hoveredId === account.id;
              const isDeleting = deletingId === account.id;

              return (
                <div
                  key={account.id}
                  onMouseEnter={() => setHoveredId(account.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  className={`
                    group relative flex items-center justify-between p-4 rounded-xl border-2
                    transition-all duration-300 ease-out
                    ${account.is_default 
                      ? "bg-gradient-to-r from-rose-50/80 to-red-50/80 dark:from-rose-950/30 dark:to-red-950/30 border-rose-200 dark:border-rose-800" 
                      : "bg-card border-transparent hover:border-rose-200/50 dark:hover:border-rose-800/50"
                    }
                    ${isDeleting ? "opacity-50 scale-[0.98]" : "opacity-100 scale-100"}
                    hover:shadow-md hover:-translate-y-0.5
                  `}
                  style={{
                    animationDelay: `${index * 50}ms`,
                  }}
                >
                  {/* Account Info */}
                  <div className="flex items-center gap-4">
                    <div className="relative">
                      <Avatar className="w-12 h-12 ring-2 ring-white dark:ring-slate-800 shadow-sm">
                        <AvatarImage
                          src={account.avatar_url}
                          alt={account.nickname || account.username}
                        />
                        <AvatarFallback className="bg-gradient-to-br from-rose-400 to-red-500 text-white font-semibold">
                          {(account.nickname || account.username || "?").charAt(0).toUpperCase()}
                        </AvatarFallback>
                      </Avatar>
                      {account.is_default && (
                        <div className="absolute -top-1 -right-1 w-5 h-5 bg-amber-400 rounded-full flex items-center justify-center shadow-sm">
                          <Star className="w-3 h-3 text-white fill-white" />
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground">
                          {account.nickname || account.username || t("未命名账号")}
                        </span>
                        <Badge
                          variant="secondary"
                          className={`${statusConfig.className} text-xs px-2 py-0.5`}
                        >
                          <StatusIcon className="w-3 h-3 mr-1 inline" />
                          {statusConfig.label}
                        </Badge>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {account.username || account.mcp_account_id}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {!account.is_default && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetDefault(account.id)}
                        className={`
                          gap-1.5 text-muted-foreground hover:text-amber-500
                          hover:bg-amber-50 dark:hover:bg-amber-950/30
                          transition-all duration-200
                          ${isHovered ? "opacity-100 translate-x-0" : "opacity-70 translate-x-1"}
                        `}
                      >
                        <Star className="w-4 h-4" />
                        <span className="hidden sm:inline">{t("设为默认")}</span>
                      </Button>
                    )}
                    
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(account.id)}
                      className={`
                        gap-1.5 text-muted-foreground hover:text-red-500
                        hover:bg-red-50 dark:hover:bg-red-950/30
                        transition-all duration-200
                        ${isHovered ? "opacity-100 translate-x-0" : "opacity-70 translate-x-1"}
                      `}
                    >
                      <Trash2 className="w-4 h-4" />
                      <span className="hidden sm:inline">{t("删除")}</span>
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
