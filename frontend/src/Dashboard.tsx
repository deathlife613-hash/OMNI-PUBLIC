import OmniCore from "./OmniCore";
import { useEffect, useState, type ReactNode } from "react";
import {
  fetchSearchStatus,
  fetchUsage,
  listConversations,
  runTool,
  type Conversation,
  type SearchStatus,
  type SystemStatus,
  type Task,
  type Usage,
} from "./api";

const fmtUptime = (s: number) => {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m ${s % 60}s`;
};

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card" aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}
const Unavailable = ({ why }: { why?: string }) => <span className="muted">Unavailable{why ? ` (${why})` : ""}</span>;

export type View = "dashboard" | "chat" | "memory" | "tools" | "agents" | "skills" | "settings";

export default function Dashboard({ status, go }: { status: SystemStatus | null; go: (v: View) => void }) {
  const [usage, setUsage] = useState<Usage | null>(null);
  const [search, setSearch] = useState<SearchStatus | null>(null);
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    const load = () => {
      void fetchUsage().then(setUsage, () => setUsage(null));
      void fetchSearchStatus().then(setSearch, () => setSearch(null));
      void listConversations().then((c) => setConvs(c.slice(0, 5)), () => undefined);
      void runTool<Task[]>("task_list").then((t) => setTasks(t.filter((x) => !x.done).slice(0, 5)), () => undefined);
    };
    load();
    const id = window.setInterval(load, 20000);
    return () => window.clearInterval(id);
  }, []);

  const ai = status?.ai;
  return (
    <main className="grid">
      <div className="hero" aria-hidden="true">
        <OmniCore size={280} points={420} ambient />
      </div>
      <Card title="Quick actions">
        <div className="row">
          <button onClick={() => go("chat")}>New chat</button>
          <button onClick={() => go("tools")}>Add task</button>
          <button onClick={() => go("memory")}>Memory</button>
          <button onClick={() => go("settings")}>Settings</button>
        </div>
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
                <span className="muted">Not tested yet</span>
              ) : ai.connected ? (
                <span className="ok">Connected</span>
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

      <Card title="Usage (since restart)">
        {usage ? (
          <dl>
            <dt>Model requests</dt>
            <dd>{usage.requests}</dd>
            <dt>Errors</dt>
            <dd>{usage.requests - usage.successful}</dd>
            <dt>Rate-limit / quota events</dt>
            <dd>{usage.rate_limit_events}</dd>
            <dt>Avg latency</dt>
            <dd>{usage.avg_latency_ms !== null ? `${usage.avg_latency_ms} ms` : <Unavailable why="no successful requests yet" />}</dd>
            <dt>Tokens (provider-reported)</dt>
            <dd>
              {usage.tokens.requests_reporting_usage
                ? `${usage.tokens.prompt} in / ${usage.tokens.completion} out`
                : <Unavailable why="provider has not reported any" />}
            </dd>
            <dt>Web searches today</dt>
            <dd>{search?.configured ? `${search.used_today} / ${search.daily_cap} (${search.cache_hits} cached)` : <Unavailable why="search not configured" />}</dd>
          </dl>
        ) : (
          <Unavailable />
        )}
      </Card>

      <Card title="Tasks & reminders">
        <ul className="plain">
          {tasks.map((t) => (
            <li key={t.id}>
              <span className="tag">{t.remind_at ? "reminder" : "task"}</span> {t.title}
            </li>
          ))}
          {tasks.length === 0 && <li className="muted">Nothing open.</li>}
        </ul>
      </Card>

      <Card title="Recent conversations">
        <ul className="plain">
          {convs.map((c) => (
            <li key={c.id}>{c.title}</li>
          ))}
          {convs.length === 0 && <li className="muted">No conversations yet.</li>}
        </ul>
      </Card>

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
            <dt>Disk free</dt>
            <dd>{status.storage ? `${status.storage.free_mb.toLocaleString()} MB` : <Unavailable />}</dd>
            <dt>Database size</dt>
            <dd>{status.storage ? `${status.storage.database_kb.toLocaleString()} KB` : <Unavailable />}</dd>
            <dt>Host RAM available</dt>
            <dd>
              {status.memory ? `${status.memory.available_mb.toLocaleString()} / ${status.memory.total_mb.toLocaleString()} MB` : <Unavailable why="not reported by this host" />}
            </dd>
          </dl>
        ) : (
          <Unavailable why="no backend connection" />
        )}
      </Card>
    </main>
  );
}
