import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap, type ChatMessage, type Job, type S } from "./client";

const ACTIVE = ["queued", "running"];

export const useSystem = () =>
  useQuery({ queryKey: ["system"], queryFn: () => unwrap(api.GET("/api/system")) });

export const useAccounts = () =>
  useQuery({ queryKey: ["accounts"], queryFn: () => unwrap(api.GET("/api/accounts")), refetchInterval: 10_000 });

export const useAccount = (id: string) =>
  useQuery({
    queryKey: ["account", id],
    queryFn: () => unwrap(api.GET("/api/accounts/{account_id}", { params: { path: { account_id: id } } })),
  });

export function useInvalidateAccount(id: string) {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["account", id] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };
}

export function useCreateAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["AccountIn"]) => unwrap(api.POST("/api/accounts", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useUpdateAccount(id: string) {
  const inv = useInvalidateAccount(id);
  return useMutation({
    mutationFn: (body: S["AccountPatch"]) =>
      unwrap(api.PATCH("/api/accounts/{account_id}", { params: { path: { account_id: id } }, body })),
    onSuccess: inv,
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/accounts/{account_id}", { params: { path: { account_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });
}

export function useRules(id: string) {
  const inv = useInvalidateAccount(id);
  const add = useMutation({
    mutationFn: (body: S["RuleIn"]) =>
      unwrap(api.POST("/api/accounts/{account_id}/rules", { params: { path: { account_id: id } }, body })),
    onSuccess: inv,
  });
  const remove = useMutation({
    mutationFn: (rule_id: string) =>
      unwrap(api.DELETE("/api/accounts/{account_id}/rules/{rule_id}", { params: { path: { account_id: id, rule_id } } })),
    onSuccess: inv,
  });
  return { add, remove };
}

export function useNotes(id: string) {
  const inv = useInvalidateAccount(id);
  return useMutation({
    mutationFn: (note_id: string) =>
      unwrap(api.DELETE("/api/accounts/{account_id}/notes/{note_id}", { params: { path: { account_id: id, note_id } } })),
    onSuccess: inv,
  });
}

/** 加 1-3 个对标账号：发起后台拆解 + 合成任务 */
export function useClone(id: string) {
  const qc = useQueryClient();
  const inv = useInvalidateAccount(id);
  return useMutation({
    mutationFn: ({ accountId, targets, names = [], theme = "" }: { targets: string[]; names?: string[]; theme?: string; accountId?: string }) =>
      unwrap(api.POST("/api/accounts/{account_id}/benchmark", {
        params: { path: { account_id: accountId ?? id } }, body: { targets, names, target: "", theme, platform: "xiaohongshu" },
      })),
    onSettled: (_d, _e, v) => { qc.invalidateQueries({ queryKey: ["jobs", v.accountId ?? id] }); inv(); },
  });
}

export function useRemoveBenchmark(id: string) {
  const inv = useInvalidateAccount(id);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (benchmark_id: string) =>
      unwrap(api.DELETE("/api/accounts/{account_id}/benchmark/{benchmark_id}", { params: { path: { account_id: id, benchmark_id } } })),
    onSuccess: () => { inv(); qc.invalidateQueries({ queryKey: ["topics", id] }); qc.invalidateQueries({ queryKey: ["jobs", id] }); },
  });
}

/** 按方向找同领域的对标候选：后台任务（半分钟到一分钟），结果存在 account.bench_candidates */
export function useFindCandidates(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ["find-cands", id],
    mutationFn: (body: { query: string; prefer: string }) =>
      unwrap(api.POST("/api/accounts/{account_id}/benchmark/candidates", { params: { path: { account_id: id } }, body })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs", id] }),
  });
}

/** 按质检意见让 AI 在这篇上再改一轮（后台任务） */
export function useRevise(draftId: string, accountId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (note: string) =>
      unwrap(api.POST("/api/drafts/{draft_id}/revise", { params: { path: { draft_id: draftId } }, body: { note } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs", accountId] }),
  });
}

export const useFindCreators = () =>
  useMutation({
    mutationFn: (q: string) => unwrap(api.GET("/api/research/creators", { params: { query: { q } } })),
  });

export const useTopics = (id: string) =>
  useQuery({
    queryKey: ["topics", id],
    queryFn: () => unwrap(api.GET("/api/accounts/{account_id}/topics", { params: { path: { account_id: id } } })),
  });

export function useTopicActions(id: string) {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: ["topics", id] });
  const search = useMutation({
    mutationFn: (direction: string) =>
      unwrap(api.POST("/api/accounts/{account_id}/topics/search", { params: { path: { account_id: id } }, body: { direction } })),
    onSuccess: inv,
  });
  const add = useMutation({
    mutationFn: (body: S["TopicIn"]) =>
      unwrap(api.POST("/api/accounts/{account_id}/topics", { params: { path: { account_id: id } }, body })),
    onSuccess: inv,
  });
  const setStatus = useMutation({
    mutationFn: ({ topic_id, status }: { topic_id: string; status: S["TopicStatus"] }) =>
      unwrap(api.PATCH("/api/accounts/{account_id}/topics/{topic_id}", {
        params: { path: { account_id: id, topic_id } }, body: { status },
      })),
    onSuccess: inv,
  });
  return { search, add, setStatus };
}

export const useDrafts = (id: string) =>
  useQuery({
    queryKey: ["drafts", id],
    queryFn: () => unwrap(api.GET("/api/accounts/{account_id}/drafts", { params: { path: { account_id: id } } })),
    refetchInterval: (q) => (q.state.data?.some((d) => d.images_busy > 0) ? 4000 : false), // 出图中：列表里的封面跟着更新
  });

export const useDraft = (id: string) =>
  useQuery({
    queryKey: ["draft", id],
    queryFn: () => unwrap(api.GET("/api/drafts/{draft_id}", { params: { path: { draft_id: id } } })),
    // 配图还在生成时自动刷新
    refetchInterval: (q) =>
      q.state.data?.images.some((i) => i.status === "pending" || i.status === "running") ? 3000 : false,
  });

export function useDraftActions(id: string) {
  const qc = useQueryClient();
  const inv = () => {
    qc.invalidateQueries({ queryKey: ["draft", id] });
    qc.invalidateQueries({ queryKey: ["drafts"] });
    qc.invalidateQueries({ queryKey: ["accounts"] });
  };
  const p = { params: { path: { draft_id: id } } };
  return {
    update: useMutation({ mutationFn: (body: S["DraftPatch"]) => unwrap(api.PATCH("/api/drafts/{draft_id}", { ...p, body })), onSuccess: inv }),
    feedback: useMutation({ mutationFn: (body: S["FeedbackIn"]) => unwrap(api.POST("/api/drafts/{draft_id}/feedback", { ...p, body })), onSuccess: inv }),
    learn: useMutation({ mutationFn: () => unwrap(api.POST("/api/drafts/{draft_id}/learn", p)) }),
    images: useMutation({
      mutationFn: (arg?: number | "all") =>
        unwrap(api.POST("/api/drafts/{draft_id}/images", {
          params: { path: { draft_id: id }, query: arg === "all" ? { all: true } : { idx: arg } },
        })),
      onSuccess: inv,
    }),
    reference: useMutation({
      mutationFn: (url: string) => unwrap(api.PUT("/api/drafts/{draft_id}/reference", { ...p, body: { url } })),
      onSuccess: (d) => { qc.setQueryData(["draft", id], d); inv(); },
    }),
    remove: useMutation({ mutationFn: () => unwrap(api.DELETE("/api/drafts/{draft_id}", p)), onSuccess: inv }),
  };
}

export function useWrite(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<S["WriteIn"]>) =>
      unwrap(api.POST("/api/accounts/{account_id}/write", { params: { path: { account_id: id } }, body: { hint: "", from_chat: false, reference_url: "", ...body } })),
    onSettled: () => qc.invalidateQueries({ queryKey: ["jobs", id] }),
  });
}

/** 账号的进行中任务，有任务时每 1.5 秒轮询；任务结束时刷新草稿/选题。 */
export function useActiveJobs(id: string) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: async () => {
      const jobs = await unwrap(api.GET("/api/jobs", { params: { query: { account_id: id } } }));
      const prev = qc.getQueryData<Job[]>(["jobs", id]) ?? [];
      const finished = prev.some((p) => ACTIVE.includes(p.status) && jobs.find((j) => j.id === p.id && !ACTIVE.includes(j.status)));
      if (finished) {
        qc.invalidateQueries({ queryKey: ["drafts", id] });
        qc.invalidateQueries({ queryKey: ["topics", id] });
        qc.invalidateQueries({ queryKey: ["draft"] });
        qc.invalidateQueries({ queryKey: ["accounts"] });
        qc.invalidateQueries({ queryKey: ["account", id] });
        qc.invalidateQueries({ queryKey: ["chat", id] });
      }
      return jobs;
    },
    refetchInterval: (q) => (q.state.data?.some((j) => ACTIVE.includes(j.status)) ? 1500 : 8000),
  });
}

export const isActive = (j: Job) => ACTIVE.includes(j.status);

export const useChat = (id: string) =>
  useQuery({
    queryKey: ["chat", id],
    queryFn: () => unwrap(api.GET("/api/accounts/{account_id}/chat", { params: { path: { account_id: id } } })),
  });

/** 正在发给小媒、还没回复的消息（工作台里任何地方发的都算，两个对话面板都能显示） */
export const usePendingChat = (id: string) =>
  useMutationState({ filters: { mutationKey: ["chat-send", id], status: "pending" }, select: (m) => m.state.variables as string });

/** 一轮对话里的一步：思考 / 调工具 / 调工具前说的话。回复的 payload.steps 里存的也是这个形状。 */
export type ChatStep = {
  id: string; kind: "thinking" | "tool" | "note"; name?: string; args?: Record<string, unknown>;
  ok?: boolean; ms?: number; error?: string; text?: string; message_id?: string; started?: number;
};
/** 正在进行的这一轮（流式）：步骤实时更新，回复逐字长出来 */
export type LiveChat = { text: string; echoed: boolean; steps: ChatStep[]; reply: string; started: number; tools: ChatMessage[] };

export const useLiveChat = (id: string) =>
  useQuery<LiveChat | null>({ queryKey: ["chat-live", id], queryFn: () => null, enabled: false, initialData: null, staleTime: Infinity, gcTime: Infinity });

type ChatEvent =
  | { type: "user" | "message"; message: ChatMessage }
  | { type: "tool_message"; id: string; message: ChatMessage }
  | ({ type: "step_start" } & ChatStep)
  | { type: "step_end"; id: string; ok: boolean; ms: number; error?: string }
  | { type: "thinking" | "note"; id: string; text: string }
  | { type: "delta"; text: string }
  | { type: "reset" } | { type: "done"; ms: number } | { type: "error"; detail: string };

/** 读 SSE：一行行 data: {...}，空行分隔 */
async function* sse(res: Response): AsyncGenerator<ChatEvent> {
  const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += value;
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
      if (data) yield JSON.parse(data) as ChatEvent;
    }
  }
}

export function useSendChat(id: string) {
  const qc = useQueryClient();
  const inv = useInvalidateAccount(id);
  const live = (fn: (l: LiveChat) => LiveChat) => qc.setQueryData<LiveChat | null>(["chat-live", id], (l) => (l ? fn(l) : l));
  const step = (sid: string, patch: Partial<ChatStep>) =>
    live((l) => ({ ...l, steps: l.steps.map((s) => (s.id === sid ? { ...s, ...patch } : s)) }));
  const addMsgs = (ms: ChatMessage[]) => qc.setQueryData<ChatMessage[]>(["chat", id], (old = []) => [...old, ...ms.filter((m) => !old.some((o) => o.id === m.id))]);
  return useMutation({
    mutationKey: ["chat-send", id],
    mutationFn: async (text: string) => {
      const init: LiveChat = { text, echoed: false, steps: [], reply: "", started: Date.now(), tools: [] };
      qc.setQueryData(["chat-live", id], init);
      try {
        const res = await fetch(`/api/accounts/${id}/chat/stream`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), credentials: "same-origin",
        });
        if (!res.ok || !res.body) {
          const body = await res.json().catch(() => ({}));
          throw new ApiError(typeof body?.detail === "string" ? body.detail : `请求失败（${res.status}）`, res.status, body);
        }
        for await (const ev of sse(res)) {
          switch (ev.type) {
            case "user": addMsgs([ev.message]); live((l) => ({ ...l, echoed: true })); break;
            case "step_start": { const { type: _t, ...st } = ev; live((l) => ({ ...l, steps: [...l.steps, { ...st, started: Date.now() }] })); break; }
            case "step_end": step(ev.id, { ok: ev.ok, ms: ev.ms, error: ev.error || undefined }); break;
            case "thinking": live((l) => ({ ...l, steps: l.steps.map((s) => (s.id === ev.id ? { ...s, text: (s.text ?? "") + ev.text } : s)) })); break;
            case "note": live((l) => ({ ...l, reply: "", steps: [...l.steps, { id: ev.id, kind: "note", text: ev.text }] })); break;
            case "delta": live((l) => ({ ...l, reply: l.reply + ev.text })); break;
            case "reset": live((l) => ({ ...l, reply: "" })); break;
            case "tool_message":
              step(ev.id, { message_id: ev.message.id });
              live((l) => ({ ...l, tools: [...l.tools, ev.message] }));
              break;
            case "message": {
              const tools = qc.getQueryData<LiveChat | null>(["chat-live", id])?.tools ?? [];
              addMsgs([...tools, ev.message]);
              qc.setQueryData(["chat-live", id], null);
              break;
            }
            case "error": throw new ApiError(ev.detail, 500, ev);
          }
        }
      } finally {
        qc.setQueryData(["chat-live", id], null);
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["chat", id] });
      qc.invalidateQueries({ queryKey: ["jobs", id] });
      qc.invalidateQueries({ queryKey: ["topics", id] });
      inv();
    },
  });
}

export const useCredentials = () =>
  useQuery({ queryKey: ["credentials"], queryFn: () => unwrap(api.GET("/api/settings/credentials")) });

export function useSaveCredentials() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, string | null>) =>
      unwrap(api.PUT("/api/settings/credentials", { body: { values } })),
    onSuccess: (d) => qc.setQueryData(["credentials"], d),
  });
}

export const useTestSources = () =>
  useMutation({
    mutationFn: (keyword: string) => unwrap(api.POST("/api/settings/sources/test", { body: { keyword } })),
  });

export const useImageSettings = () =>
  useQuery({ queryKey: ["image-settings"], queryFn: () => unwrap(api.GET("/api/settings/image")) });

export function useSaveImageSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { api_key?: string | null; model?: string | null; use_refs?: boolean }) =>
      unwrap(api.PUT("/api/settings/image", { body })),
    onSuccess: (d) => {
      qc.setQueryData(["image-settings"], d);
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });
}

export const useTestImage = () =>
  useMutation({
    mutationFn: (body: { api_key?: string | null; model?: string | null }) => unwrap(api.POST("/api/settings/image/test", { body })),
  });

export const useLlmSettings = () =>
  useQuery({ queryKey: ["llm-settings"], queryFn: () => unwrap(api.GET("/api/settings/llm")) });

/** 保存前后端会先用这个 Key 实际问一句，填错直接报错 */
export function useSaveLlmKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (api_key: string) => unwrap(api.PUT("/api/settings/llm", { body: { api_key } })),
    onSuccess: (d) => {
      qc.setQueryData(["llm-settings"], d);
      qc.invalidateQueries({ queryKey: ["system"] });
    },
  });
}

// ─── 登录（在线版） ─────────────────────────────────────────────────────────

export type Me = S["MeOut"];

/** 我是谁；在线版没登录时是 null（页面显示登录框）。本地版永远是默认用户。 */
export const useMe = () =>
  useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const { data, response } = await api.GET("/api/auth/me");
      if (response.status === 401) return null;
      if (!response.ok || !data) throw new ApiError(`请求失败（${response.status}）`, response.status, null);
      return data;
    },
    retry: false,
  });

/** 管理员才能改全站设置（Key、平台账号）；本地版自己就是管理员 */
export const useIsAdmin = () => useMe().data?.is_admin ?? false;

/** 换人登录时清掉上一个人的数据缓存；["me"] 本身保留（clear() 会让正在订阅它的组件收不到更新） */
const dropOthers = (qc: ReturnType<typeof useQueryClient>) => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: S["LoginIn"]) => unwrap(api.POST("/api/auth/login", { body })),
    onSuccess: (me) => { dropOthers(qc); qc.setQueryData(["me"], me); },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSuccess: () => { dropOthers(qc); qc.setQueryData(["me"], null); },
  });
}

/** 演示版：输入管理员口令 / 退出管理员 */
export function useAdminUnlock() {
  const qc = useQueryClient();
  return {
    unlock: useMutation({
      mutationFn: (token: string) => unwrap(api.POST("/api/auth/unlock", { body: { token } })),
      onSuccess: (me) => qc.setQueryData(["me"], me),
    }),
    lock: useMutation({
      mutationFn: () => unwrap(api.POST("/api/auth/lock")),
      onSuccess: (me) => qc.setQueryData(["me"], me),
    }),
  };
}

export const useChangePassword = () =>
  useMutation({ mutationFn: (body: S["PasswordIn"]) => unwrap(api.POST("/api/auth/password", { body })) });

export const useUsers = () => useQuery({ queryKey: ["users"], queryFn: () => unwrap(api.GET("/api/admin/users")) });

export function useUserActions() {
  const qc = useQueryClient();
  const inv = () => qc.invalidateQueries({ queryKey: ["users"] });
  return {
    add: useMutation({ mutationFn: (body: S["UserIn"]) => unwrap(api.POST("/api/admin/users", { body })), onSuccess: inv }),
    update: useMutation({
      mutationFn: ({ id, ...body }: S["UserPatch"] & { id: string }) =>
        unwrap(api.PATCH("/api/admin/users/{user_id}", { params: { path: { user_id: id } }, body })),
      onSuccess: inv,
    }),
  };
}
