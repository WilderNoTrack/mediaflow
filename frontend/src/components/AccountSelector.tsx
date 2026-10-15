import * as React from "react";
import { Star, User } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/app/components/ui/select";
import { cn } from "@/app/components/ui/utils";

// Account data structure based on project conventions
export interface Account {
  id: string;
  mcp_account_id?: string;
  name?: string;
  nickname?: string;
  username?: string;
  avatar_url?: string;
  is_default?: boolean;
  status?: string;
  fans_count?: number;
}

export interface AccountSelectorProps {
  /** Array of account objects */
  accounts: Account[];
  /** Currently selected account ID */
  selectedAccountId: string | null;
  /** Callback when account is selected */
  onSelect: (accountId: string) => void;
  /** Optional disabled state */
  disabled?: boolean;
  /** Optional placeholder text */
  placeholder?: string;
  /** Optional className for the container */
  className?: string;
  /** Optional empty state message */
  emptyMessage?: string;
}

/**
 * AccountSelector - Dropdown selector for choosing among multiple Xiaohongshu accounts
 * 
 * Features:
 * - Displays account avatar with fallback to user icon
 * - Shows account name/nickname
 * - Indicates default account with star icon
 * - Handles empty state
 * - Fully controlled component (no internal state management)
 * - Uses shadcn/ui Select component for consistency
 */
export function AccountSelector({
  accounts,
  selectedAccountId,
  onSelect,
  disabled = false,
  placeholder = "选择账号",
  className,
  emptyMessage = "暂无账号",
}: AccountSelectorProps) {
  // Get the selected account for displaying in trigger
  const selectedAccount = accounts.find((acc) => acc.id === selectedAccountId);

  // Determine display name for an account
  const getDisplayName = (account: Account): string => {
    return account.nickname || account.name || account.username || "未命名账号";
  };

  // Avatar component with fallback
  const AccountAvatar = ({ account, size = "sm" }: { account?: Account; size?: "sm" | "md" }) => {
    const sizeClasses = size === "sm" ? "w-5 h-5" : "w-8 h-8";
    const iconSize = size === "sm" ? "w-3 h-3" : "w-4 h-4";
    
    if (account?.avatar_url) {
      return (
        <img
          src={account.avatar_url}
          alt={getDisplayName(account)}
          className={cn(
            sizeClasses,
            "rounded-full object-cover border border-border/50",
            disabled && "opacity-50"
          )}
        />
      );
    }
    
    return (
      <div
        className={cn(
          sizeClasses,
          "rounded-full bg-gradient-to-br from-pink-400 to-red-500 flex items-center justify-center text-white",
          disabled && "opacity-50"
        )}
      >
        <User className={cn(iconSize, "text-white/90")} />
      </div>
    );
  };

  // If there are no accounts, show disabled selector with empty message
  if (accounts.length === 0) {
    return (
      <div className={cn("w-full", className)}>
        <Select disabled value="">
          <SelectTrigger className="w-full">
            <div className="flex items-center gap-2 text-muted-foreground">
              <div className="w-5 h-5 rounded-full bg-muted flex items-center justify-center">
                <User className="w-3 h-3 text-muted-foreground" />
              </div>
              <SelectValue placeholder={emptyMessage} />
            </div>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="" disabled>
              {emptyMessage}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
    );
  }

  return (
    <div className={cn("w-full", className)}>
      <Select
        value={selectedAccountId || ""}
        onValueChange={onSelect}
        disabled={disabled}
      >
        <SelectTrigger
          className={cn(
            "w-full transition-all duration-200",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <div className="flex items-center gap-2 overflow-hidden">
            {selectedAccount ? (
              <>
                <AccountAvatar account={selectedAccount} size="sm" />
                <span className="truncate">{getDisplayName(selectedAccount)}</span>
                {selectedAccount.is_default && (
                  <Star className="w-3 h-3 text-yellow-500 fill-yellow-500 flex-shrink-0" />
                )}
              </>
            ) : (
              <span className="text-muted-foreground">{placeholder}</span>
            )}
          </div>
        </SelectTrigger>
        <SelectContent className="w-full min-w-[200px]">
          {accounts.map((account) => (
            <SelectItem
              key={account.id}
              value={account.id}
              className="cursor-pointer transition-colors hover:bg-accent focus:bg-accent"
            >
              <div className="flex items-center gap-3 py-1">
                <AccountAvatar account={account} size="md" />
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium truncate">
                      {getDisplayName(account)}
                    </span>
                    {account.is_default && (
                      <Star className="w-3 h-3 text-yellow-500 fill-yellow-500 flex-shrink-0" />
                    )}
                  </div>
                  {account.username && account.username !== getDisplayName(account) && (
                    <span className="text-xs text-muted-foreground truncate">
                      @{account.username}
                    </span>
                  )}
                </div>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default AccountSelector;
