import { LogOut, UserRound, Users } from "lucide-react";
import { useState } from "react";
import { useChangePassword, useLogout, useMe } from "../api/hooks";
import { cn } from "../lib/utils";
import { Button, ErrorText, Input, Label, Modal } from "./ui";
import { UsersDialog } from "./UsersDialog";

/** 在线版右上角：我是谁、今天还能写几篇、改密码、退出；管理员多一个「成员管理」。本地版不显示。 */
export function UserMenu() {
  const { data: me } = useMe();
  const logout = useLogout();
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState(false);
  const [pw, setPw] = useState(false);
  if (!me || me.auth !== "password") return null;
  const lim = me.limits as { writes?: number };
  const used = me.usage as { writes?: number };
  return (
    <div className="relative">
      <Button variant="outline" size="sm" onClick={() => setOpen(!open)}><UserRound /><span className="hidden max-w-24 truncate sm:inline">{me.name}</span></Button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 z-50 mt-2 w-56 rounded-xl border bg-card p-1.5 text-sm shadow-xl">
            <div className="px-3 py-2">
              <div className="font-medium">{me.name}</div>
              <div className="text-xs text-muted-foreground">
                {me.username}{me.is_admin ? " · 管理员" : lim.writes ? ` · 今天还能写 ${Math.max(0, lim.writes - (used.writes ?? 0))} 篇` : ""}
              </div>
            </div>
            {me.is_admin && <Item onClick={() => { setUsers(true); setOpen(false); }}><Users />成员管理</Item>}
            <Item onClick={() => { setPw(true); setOpen(false); }}><UserRound />改密码</Item>
            <Item onClick={() => logout.mutate()} className="text-red-600"><LogOut />退出登录</Item>
          </div>
        </>
      )}
      {users && <UsersDialog onClose={() => setUsers(false)} />}
      {pw && <PasswordDialog onClose={() => setPw(false)} />}
    </div>
  );
}

function Item({ onClick, className, children }: { onClick: () => void; className?: string; children: React.ReactNode }) {
  return (
    <button onClick={onClick} className={cn("flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-muted [&_svg]:size-4", className)}>{children}</button>
  );
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const change = useChangePassword();
  const [oldPw, setOld] = useState("");
  const [newPw, setNew] = useState("");
  return (
    <Modal onClose={onClose}>
      <form className="space-y-4 p-5" onSubmit={(e) => { e.preventDefault(); change.mutate({ old_password: oldPw, new_password: newPw }, { onSuccess: onClose }); }}>
        <div className="font-semibold">改密码</div>
        <div><Label>原密码</Label><Input type="password" autoComplete="current-password" value={oldPw} onChange={(e) => setOld(e.target.value)} /></div>
        <div><Label hint="至少 8 位">新密码</Label><Input type="password" autoComplete="new-password" value={newPw} onChange={(e) => setNew(e.target.value)} /></div>
        <ErrorText error={change.error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
          <Button type="submit" variant="gradient" loading={change.isPending} disabled={!oldPw || newPw.length < 8}>保存</Button>
        </div>
      </form>
    </Modal>
  );
}
