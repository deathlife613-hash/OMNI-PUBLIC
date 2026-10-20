import { useCallback, useEffect, useState } from "react";
import { fetchAudit, setToken, testProvider, type AuditEntry, type LastTest, type SystemStatus } from "./api";

export type Theme = "dark" | "light" | "system";
const KEY = "omni.theme";
export const loadTheme = (): Theme => {
  try {
    const t = localStorage.getItem(KEY);
    if (t === "dark" || t === "light" || t === "system") return t;
  } catch {
    /* ignore */
  }
  return "dark";
};
export function applyTheme(t: Theme): void {
  const light = t === "light" || (t === "system" && window.matchMedia?.("(prefers-color-scheme: light)").matches);
  document.documentElement.dataset.theme = light ? "light" : "dark";
  try {
    localStorage.setItem(KEY, t);
  } catch {
    /* ignore */
  }
}

export default function Settings({ status, go }: { status: SystemStatus | null; go: (v: "memory" | "chat") => void }) {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [test, setTest] = useState<LastTest | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    fetchAudit().then(setAudit, (e) => setErr(e instanceof Error ? e.message : "Could not load activity."));
  }, []);
  useEffect(load, [load]);

  const ai = status?.ai;
  const integ = status?.integrations;
  return (
    <div className="stack">
      <section className="card" aria-label="Appearance">
        <h2>Appearance</h2>
        <label htmlFor="theme">Theme</label>
        <select
          id="theme"
          value={theme}
          onChange={(e) => {
            const t = e.target.value as Theme;
            setTheme(t);
            applyTheme(t);
          }}
        >
          <option value="dark">Dark</option>
          <option value="light">Light</option>
          <option value="system">Match system</option>
        </select>
      </section>

      <section className="card" aria-label="AI model">
        <h2>AI model</h2>
        <dl>
          <dt>Provider</dt>
          <dd>{ai?.provider ?? "—"}</dd>
          <dt>Model</dt>
          <dd>{ai?.model ?? "Not selected"}</dd>
          <dt>Key</dt>
          <dd>{ai?.api_key_configured ? "Configured on the server (never shown here)" : "Not configured"}</dd>
          <dt>Paid providers</dt>
          <dd>{ai?.paid_providers_allowed ? "Allowed" : "Blocked"}</dd>
        </dl>
        <p className="muted">
          Provider, endpoint and key are set on the server (environment variables) so secrets never reach the browser. Pick the model in Chat.
        </p>
        <div className="row">
          <button onClick={() => testProvider().then(setTest, (e) => setErr(e instanceof Error ? e.message : "Test failed."))}>Test connection</button>
          <button onClick={() => go("chat")}>Choose model in Chat</button>
        </div>
        {test && <p role="status" className={test.ok ? "ok" : "error"}>{test.ok ? `Connected (${test.latency_ms} ms).` : `Failed (${test.kind}): ${test.message}`}</p>}
      </section>

      <section className="card" aria-label="Integrations">
        <h2>Integrations</h2>
        <dl>
          <dt>Web search</dt>
          <dd>{integ?.search.configured ? `Enabled (${integ.search.provider ?? "custom"})` : "Not configured"}</dd>
          <dt>Documents folder</dt>
          <dd>{integ?.documents.enabled ? "Enabled (read-only)" : "Not configured"}</dd>
        </dl>
      </section>

      <section className="card" aria-label="Data and backup">
        <h2>Data &amp; backup</h2>
        <p className="muted">Export or restore conversations, memories and notes from the Memory tab. Backups never include keys or tokens.</p>
        <button onClick={() => go("memory")}>Open backup tools</button>
      </section>

      <section className="card" aria-label="Security">
        <h2>Security</h2>
        <dl>
          <dt>Access token</dt>
          <dd>{status?.auth.token_required ? "Required" : "Not required (development only)"}</dd>
          <dt>Environment</dt>
          <dd>{status?.environment ?? "—"}</dd>
        </dl>
        <button
          onClick={() => {
            setToken("");
            window.location.reload();
          }}
        >
          Sign out of this tab
        </button>
      </section>

      <section className="card" aria-label="Recent activity">
        <h2>Recent tool activity</h2>
        {err && <p role="alert" className="error">{err}</p>}
        <ul className="plain">
          {audit.slice(0, 15).map((a) => (
            <li key={a.id}>
              <span className="tag">{a.outcome}</span> {a.tool} <span className="muted">{new Date(a.at).toLocaleString()}</span>
            </li>
          ))}
          {audit.length === 0 && <li className="muted">No activity yet.</li>}
        </ul>
      </section>
    </div>
  );
}
