import { useCallback, useEffect, useState, type FormEvent } from "react";
import Chat from "./Chat";
import OmniCore from "./OmniCore";
import Dashboard, { type View } from "./Dashboard";
import Settings, { applyTheme, loadTheme } from "./Settings";
import MemoryCenter from "./Memory";
import Tools from "./Tools";
import Agents from "./Agents";
import Skills from "./Skills";
import { ApiError, fetchHealth, fetchStatus, runTool, setToken, type SystemStatus, type Task } from "./api";

type Conn = "checking" | "online" | "offline" | "locked";

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
  const [view, setView] = useState<View>("dashboard");

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
    applyTheme(loadTheme());
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

  return (
    <div className="shell">
      <header className="top">
        <div className="brand">
          <OmniCore size={34} points={70} className="brand-core" />
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
          <button className={view === "agents" ? "on" : ""} onClick={() => setView("agents")}>
            Agents
          </button>
          <button className={view === "skills" ? "on" : ""} onClick={() => setView("skills")}>
            Skills
          </button>
          <button className={view === "settings" ? "on" : ""} onClick={() => setView("settings")}>
            Settings
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
      ) : view === "agents" ? (
        <Agents />
      ) : view === "skills" ? (
        <Skills />
      ) : view === "settings" ? (
        <Settings status={status} go={setView} />
      ) : (
      <Dashboard status={status} go={setView} />
      )}
    </div>
  );
}
