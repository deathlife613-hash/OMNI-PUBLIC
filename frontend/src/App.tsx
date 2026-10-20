import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import Chat from "./Chat";
import MemoryCenter from "./Memory";
import Tools from "./Tools";
import { ApiError, fetchHealth, fetchStatus, runTool, setToken, type SystemStatus, type Task } from "./api";

type Conn = "checking" | "online" | "offline" | "locked";

const fmtUptime = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
};

function Card({ title, children, phase }: { title: string; children: ReactNode; phase?: string }) {
  return (
    <section className="card" aria-label={title}>
      <h2>
        {title}
        {phase && <span className="tag">{phase}</span>}
      </h2>
      {children}
    </section>
  );
}

const Unavailable = ({ why }: { why?: string }) => (
  <span className="muted">Unavailable{why ? ` (${why})` : ""}</span>
);

function Login({ onSubmit, error }: { onSubmit: (t: string) => void; error: string }) {
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(value.trim());
  };
  return (
    <main className="login">
      <form onSubmit={submit} className="card">
        <h1>OMNI</h1>
        <p className="muted">Enter your access token to continue.</p>
        <label htmlFor="token">Access token</label>
        <input
          id="token"
          type="password"
          autoComplete="current-password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          autoFocus
        />
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <button type="submit" disabled={!value.trim()}>
          Unlock
        </button>
      </form>
    </main>
  );
}

export default function App() {
  const [conn, setConn] = useState<Conn>("checking");
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState("");
  const [due, setDue] = useState<Task[]>([]);
  const [view, setView] = useState<"dashboard" | "chat" | "memory" | "tools">("dashboard");

  const refresh = useCallback(async () => {
    try {
      await fetchHealth();
    } catch {
      setConn("offline");
      setError("Cannot reach the OMNI backend. Is it running?");
      return;
    }
    try {
      setStatus(await fetchStatus());
      setConn("online");
      setError("");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 429)) {
        setConn("locked");
        setError(e.status === 429 ? e.message : "");
      } else {
        setConn("offline");
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (conn !== "online") return;
    const poll = () => void runTool<Task[]>("reminders_due").then(setDue, () => undefined);
    poll();
    const id = window.setInterval(poll, 30000);
    return () => window.clearInterval(id);
  }, [conn]);

  const unlock = (t: string) => {
    setToken(t);
    setConn("checking");
    void refresh().then(() => undefined);
  };

  if (conn === "locked") {
    return <Login onSubmit={unlock} error={error || "Enter the token set in OMNI_ACCESS_TOKEN."} />;
  }

  const ai = status?.ai;
  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <span className="orb" aria-hidden="true" />
          <strong>OMNI</strong>
          <span className="muted">v{status?.version ?? "—"}</span>
        </div>
        <nav className="tabs" aria-label="Views">
          <button className={view === "dashboard" ? "on" : ""} onClick={() => setView("dashboard")}>
            Dashboard
          </button>
          <button className={view === "chat" ? "on" : ""} onClick={() => setView("chat")}>
            Chat
          </button>
          <button className={view === "memory" ? "on" : ""} onClick={() => setView("memory")}>
            Memory
          </button>
          <button className={view === "tools" ? "on" : ""} onClick={() => setView("tools")}>
            Tools
          </button>
        </nav>
        <div className={`pill ${conn}`} role="status">
          {conn === "online" ? "Backend connected" : conn === "checking" ? "Connecting…" : "Backend offline"}
        </div>
      </header>

      {error && conn === "offline" && (
        <p role="alert" className="banner">
          {error}
        </p>
      )}

      {due.length > 0 && (
        <p role="alert" className="banner">
          Reminder: {due.map((d) => d.title).join(" · ")} —{" "}
          <button className="link small" onClick={() => setView("tools")}>open</button>
        </p>
      )}

      {view === "chat" ? (
        <Chat status={status} onStatusChange={() => void refresh()} />
      ) : view === "memory" ? (
        <MemoryCenter />
      ) : view === "tools" ? (
        <Tools />
      ) : (
      <main className="grid">
        <Card title="System">
          {status ? (
            <dl>
              <dt>Environment</dt>
              <dd>{status.environment}</dd>
              <dt>Uptime</dt>
              <dd>{fmtUptime(status.uptime_seconds)}</dd>
              <dt>Database</dt>
              <dd>
                {status.database.engine} — {status.database.ok ? "ok" : "unavailable"}
              </dd>
              <dt>Auth</dt>
              <dd>{status.auth.token_required ? "Token required" : "Open (development only)"}</dd>
            </dl>
          ) : (
            <Unavailable why="no backend connection" />
          )}
        </Card>

        <Card title="AI model">
          {ai ? (
            <dl>
              <dt>Provider</dt>
              <dd>{ai.provider}</dd>
              <dt>Model</dt>
              <dd>{ai.model ?? <span className="muted">Not selected yet</span>}</dd>
              <dt>API key</dt>
              <dd>{ai.api_key_configured ? "Configured on server" : "Not configured"}</dd>
              <dt>Connection</dt>
              <dd>
                {ai.connected === null ? (
                  <span className="muted">Not tested yet (use Chat → Test connection)</span>
                ) : ai.connected ? (
                  <span style={{ color: "var(--good)" }}>Connected</span>
                ) : (
                  <span className="error">Failed: {ai.last_test?.message ?? "unknown"}</span>
                )}
              </dd>
              <dt>Paid providers</dt>
              <dd>{ai.paid_providers_allowed ? "Allowed" : "Blocked"}</dd>
            </dl>
          ) : (
            <Unavailable />
          )}
        </Card>

        <Card title="Storage & memory">
          {status ? (
            <dl>
              <dt>Disk free</dt>
              <dd>{status.storage ? `${status.storage.free_mb.toLocaleString()} MB` : <Unavailable />}</dd>
              <dt>Database size</dt>
              <dd>{status.storage ? `${status.storage.database_kb.toLocaleString()} KB` : <Unavailable />}</dd>
              <dt>Host RAM available</dt>
              <dd>
                {status.memory ? (
                  `${status.memory.available_mb.toLocaleString()} / ${status.memory.total_mb.toLocaleString()} MB`
                ) : (
                  <Unavailable why="not reported by this host" />
                )}
              </dd>
            </dl>
          ) : (
            <Unavailable />
          )}
        </Card>

        <Card title="Conversations">
          <p className="muted">Open the Chat tab to start or continue a conversation.</p>
        </Card>
        <Card title="Tasks & reminders" phase="Phase 5">
          <p className="muted">Not implemented yet.</p>
        </Card>
        <Card title="Voice" phase="Phase 4">
          <button disabled>Microphone</button> <button disabled>Speech output</button>
          <p className="muted">Controls are disabled until voice is built.</p>
        </Card>
      </main>
      )}
    </div>
  );
}
