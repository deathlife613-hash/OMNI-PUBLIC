import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  agentLimits, cancelAgentTask, createAgentTask, decideApproval, deleteAgentTask, getAgentTask, listAgentTasks,
  pendingApprovals, runAgentTask, workspaceFile, workspaceTree,
  type AgentApproval, type AgentLimits, type AgentTask,
} from "./api";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");
const RESUMABLE = ["queued", "paused", "paused_quota", "failed"];

export default function Agents() {
  const [limits, setLimits] = useState<AgentLimits | null>(null);
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [open, setOpen] = useState<AgentTask | null>(null);
  const [goal, setGoal] = useState("");
  const [running, setRunning] = useState<string | null>(null);
  const [approvals, setApprovals] = useState<AgentApproval[]>([]);
  const [files, setFiles] = useState<string[] | null>(null);
  const [fileText, setFileText] = useState<{ path: string; text: string } | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [l, t, a] = await Promise.all([agentLimits(), listAgentTasks(), pendingApprovals()]);
      setLimits(l); setTasks(t); setApprovals(a);
      if (l.workspace_configured) setFiles((await workspaceTree()).files);
    } catch (e) { setErr(msg(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const show = async (id: string) => { try { setOpen(await getAgentTask(id)); } catch (e) { setErr(msg(e)); } };

  const run = async (id: string) => {
    setErr(""); setRunning(id);
    try {
      await runAgentTask(id, () => void show(id));
    } catch (e) { setErr(msg(e)); }
    setRunning(null);
    await load(); await show(id);
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!goal.trim()) return;
    try {
      const t = await createAgentTask(goal.trim());
      setGoal("");
      await load();
      void run(t.id);
    } catch (er) { setErr(msg(er)); }
  };

  const decide = async (id: number, action: "approve" | "reject" | "revert") => {
    try { await decideApproval(id, action); await load(); if (open) await show(open.id); } catch (e) { setErr(msg(e)); }
  };

  return (
    <div className="stack">
      {err && <p role="alert" className="error">{err}</p>}
      <section className="card" aria-label="Agent limits">
        <h2>Agents</h2>
        {limits && (
          <p className="muted">
            Runs one step at a time on one model. Limits per task: {limits.max_steps} steps, {limits.max_model_calls} model calls, {limits.max_seconds_per_run}s per run.
            No commands are ever executed; file edits need your approval. Not enabled: {limits.not_enabled.join(", ")}.
          </p>
        )}
        <form onSubmit={(e) => void create(e)} className="row">
          <input aria-label="Agent goal" placeholder="Give the team a goal…" value={goal} maxLength={2000} onChange={(e) => setGoal(e.target.value)} />
          <button type="submit" disabled={!goal.trim() || !!running}>Start</button>
        </form>
      </section>

      {approvals.length > 0 && (
        <section className="card" aria-label="Approval queue">
          <h2>Waiting for your approval</h2>
          {approvals.map((a) => (
            <div key={a.id}>
              <strong>{a.path}</strong>
              <pre className="diff">{a.diff}</pre>
              <div className="row">
                <button onClick={() => void decide(a.id, "approve")}>Approve &amp; write file</button>
                <button onClick={() => void decide(a.id, "reject")}>Reject</button>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="card" aria-label="Tasks">
        <h2>Tasks</h2>
        <ul className="plain">
          {tasks.map((t) => (
            <li key={t.id}>
              <button className="link" onClick={() => void show(t.id)}>{t.goal.slice(0, 70)}</button>
              <span className="tag">{t.status}</span>
              <span className="spacer" />
              {RESUMABLE.includes(t.status) && <button className="link small" disabled={!!running} onClick={() => void run(t.id)}>{t.status === "queued" ? "Run" : "Resume"}</button>}
              {(t.status === "running" || RESUMABLE.includes(t.status)) && <button className="link small" onClick={() => void cancelAgentTask(t.id).then(load, (e) => setErr(msg(e)))}>Cancel</button>}
              {t.status !== "running" && <button className="link small" onClick={() => window.confirm("Delete this task?") && void deleteAgentTask(t.id).then(() => { setOpen(null); return load(); }, (e) => setErr(msg(e)))}>Delete</button>}
            </li>
          ))}
          {tasks.length === 0 && <li className="muted">No tasks yet.</li>}
        </ul>
      </section>

      {open && (
        <section className="card" aria-label="Task detail">
          <h2>{open.goal.slice(0, 60)}</h2>
          <p className="muted">Status: {open.status} · model calls used: {open.model_calls}</p>
          {open.error && <p role="alert" className="error">{open.error}</p>}
          <ol>
            {open.steps?.map((s) => (
              <li key={s.idx}>
                <strong>{s.role}</strong> <span className="tag">{s.status}</span>
                <div className="muted">{s.instruction}</div>
                {s.output && <div style={{ whiteSpace: "pre-wrap" }}>{s.output}</div>}
              </li>
            ))}
          </ol>
          {open.summary && <p><strong>Summary:</strong> {open.summary}</p>}
          {open.approvals?.filter((a) => a.status === "applied").map((a) => (
            <div className="row" key={a.id}>Applied: {a.path} <button className="link small" onClick={() => void decide(a.id, "revert")}>Revert</button></div>
          ))}
        </section>
      )}

      <section className="card" aria-label="Workspace">
        <h2>Workspace (read-only)</h2>
        {!limits?.workspace_configured ? (
          <p className="muted">No workspace authorized. Set OMNI_WORKSPACE_DIR on the server to a project folder.</p>
        ) : (
          <div className="row" style={{ alignItems: "flex-start" }}>
            <ul className="plain" style={{ flex: 1, maxHeight: 240, overflow: "auto" }}>
              {files?.map((f) => (
                <li key={f}><button className="link small" onClick={() => void workspaceFile(f).then((r) => setFileText({ path: f, text: r.text }), (e) => setErr(msg(e)))}>{f}</button></li>
              ))}
            </ul>
            {fileText && <pre className="diff" style={{ flex: 2 }} aria-label={fileText.path}>{fileText.text}</pre>}
          </div>
        )}
      </section>
    </div>
  );
}
