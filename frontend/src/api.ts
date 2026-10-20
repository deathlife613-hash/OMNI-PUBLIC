// The only module that talks to the backend. The OMNI access token (the owner's login)
// is kept in sessionStorage for the tab's lifetime. Model-provider keys never reach the
// browser: the backend holds them and the API exposes only booleans.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const TOKEN_KEY = "omni.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public kind?: string,
  ) {
    super(message);
  }
}

export const getToken = (): string => {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
};

export const setToken = (t: string): void => {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: token lives only until reload */
  }
};

function headers(json: boolean): Record<string, string> {
  const h: Record<string, string> = {};
  const token = getToken();
  if (token) h.Authorization = `Bearer ${token}`;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function toError(res: Response): Promise<ApiError> {
  let message = res.statusText;
  let kind: string | undefined;
  try {
    const body = await res.json();
    const d = body.detail;
    if (typeof d === "string") message = d;
    else if (d && typeof d === "object") {
      message = d.message ?? message;
      kind = d.kind;
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, message, kind);
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: headers(body !== undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the OMNI backend.");
  }
  if (!res.ok) throw await toError(res);
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: string;
}

export interface LastTest {
  ok: boolean;
  kind?: string;
  message?: string;
  models_available?: number;
  latency_ms: number;
  checked_at: string;
}

export interface SystemStatus {
  name: string;
  version: string;
  environment: string;
  uptime_seconds: number;
  database: { ok: boolean; engine: string };
  storage: { free_mb: number; total_mb: number; database_kb: number } | null;
  memory: { total_mb: number; available_mb: number } | null;
  ai: {
    provider: string;
    model: string | null;
    api_key_configured: boolean;
    connected: boolean | null;
    last_test: LastTest | null;
    paid_providers_allowed: boolean;
  };
  auth: { token_required: boolean };
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}
export interface Msg {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}
export interface ModelEntry {
  id: string;
  context_window: number | null;
}

export const fetchHealth = () => request<Health>("/api/health");
export const fetchStatus = () => request<SystemStatus>("/api/status");
export const listConversations = () => request<Conversation[]>("/api/conversations");
export const createConversation = () => request<Conversation>("/api/conversations", "POST", {});
export const getConversation = (id: string) =>
  request<Conversation & { messages: Msg[] }>(`/api/conversations/${id}`);
export const deleteConversation = (id: string) => request<void>(`/api/conversations/${id}`, "DELETE");
export const fetchModels = () => request<{ models: ModelEntry[] }>("/api/provider/models");
export const selectModel = (model: string) => request<{ model: string }>("/api/provider/model", "PUT", { model });
export const testProvider = () => request<LastTest>("/api/provider/test", "POST");

export interface Source {
  title: string;
  url: string;
}

export interface StreamError {
  kind: string;
  message: string;
  retry_after?: number | null;
}

/** POSTs a message and streams the reply. Resolves with an error object (never throws) for
 *  provider problems, so the UI can show them without losing the conversation. */
export async function streamMessage(
  conversationId: string,
  content: string,
  onDelta: (text: string) => void,
  signal?: AbortSignal,
  opts: { useSearch?: boolean; onNotice?: (m: string) => void; onSources?: (s: Source[]) => void } = {},
): Promise<StreamError | null> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api/conversations/${conversationId}/messages`, {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify({ content, use_search: !!opts.useSearch }),
      signal,
    });
  } catch {
    return { kind: "network", message: "Cannot reach the OMNI backend." };
  }
  if (!res.ok || !res.body) {
    const e = await toError(res);
    return { kind: e.kind ?? "http", message: e.message };
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const ev = /^event: (.*)$/m.exec(block)?.[1];
        const raw = /^data: (.*)$/m.exec(block)?.[1];
        if (!ev || !raw) continue;
        const data = JSON.parse(raw);
        if (ev === "delta") onDelta(data.text as string);
        else if (ev === "notice") opts.onNotice?.(data.message as string);
        else if (ev === "done") opts.onSources?.((data.sources ?? []) as Source[]);
        else if (ev === "error") return data as StreamError;
      }
    }
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") return { kind: "cancelled", message: "Stopped." };
    return { kind: "network", message: "The connection was interrupted." };
  }
  return null;
}

export interface Memory {
  id: number;
  kind: "fact" | "preference";
  content: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}
export interface Note {
  id: number;
  title: string;
  body: string;
  updated_at: string;
}
const qs = (q: string) => (q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "");
export const listMemories = (q = "") => request<Memory[]>(`/api/memories${qs(q)}`);
export const createMemory = (content: string, kind: Memory["kind"] = "fact") =>
  request<Memory>("/api/memories", "POST", { content, kind });
export const patchMemory = (id: number, patch: Partial<Pick<Memory, "content" | "kind" | "enabled">>) =>
  request<Memory>(`/api/memories/${id}`, "PATCH", patch);
export const deleteMemory = (id: number) => request<void>(`/api/memories/${id}`, "DELETE");
export const getMemorySettings = () => request<{ enabled: boolean }>("/api/memory/settings");
export const putMemorySettings = (enabled: boolean) =>
  request<{ enabled: boolean }>("/api/memory/settings", "PUT", { enabled });
export const listNotes = (q = "") => request<Note[]>(`/api/notes${qs(q)}`);
export const createNote = (title: string, body: string) => request<Note>("/api/notes", "POST", { title, body });
export const patchNote = (id: number, patch: Partial<Pick<Note, "title" | "body">>) =>
  request<Note>(`/api/notes/${id}`, "PATCH", patch);
export const deleteNote = (id: number) => request<void>(`/api/notes/${id}`, "DELETE");
export const exportAll = () => request<Record<string, unknown>>("/api/export");
export const restoreBackup = (backup: Record<string, unknown>) =>
  request<{ restored: Record<string, number> }>("/api/restore", "POST", { confirm: true, backup });

export interface Task {
  id: number;
  title: string;
  due_at: string | null;
  remind_at: string | null;
  done: boolean;
}
export async function runTool<T = unknown>(name: string, args: Record<string, unknown> = {}, confirm = false): Promise<T> {
  return (await request<{ result: T }>(`/api/tools/${name}/run`, "POST", { args, confirm })).result;
}
