// The only module that talks to the backend. The OMNI access token (the owner's login)
// is kept in sessionStorage for the tab's lifetime. Model-provider keys never reach the
// browser: the backend holds them and /api/status exposes only booleans.
const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const TOKEN_KEY = "omni.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
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

async function request<T>(path: string): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
  } catch {
    throw new ApiError(0, "Cannot reach the OMNI backend.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  database: string;
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
    paid_providers_allowed: boolean;
  };
  auth: { token_required: boolean };
}

export const fetchHealth = () => request<Health>("/api/health");
export const fetchStatus = () => request<SystemStatus>("/api/status");
