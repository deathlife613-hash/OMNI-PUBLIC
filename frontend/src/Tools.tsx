import { useCallback, useEffect, useState, type FormEvent } from "react";
import { runTool, type Task } from "./api";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "");

export default function Tools() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [title, setTitle] = useState("");
  const [at, setAt] = useState("");
  const [asReminder, setAsReminder] = useState(false);
  const [expr, setExpr] = useState("");
  const [calc, setCalc] = useState("");
  const [dq, setDq] = useState("");
  const [docs, setDocs] = useState<{ path: string; snippet: string }[] | null>(null);
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      setTasks(await runTool<Task[]>("task_list"));
    } catch (e) {
      setErr(msg(e));
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setErr("");
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(msg(e));
    }
  };

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    const iso = at ? new Date(at).toISOString() : null;
    void act(async () => {
      if (asReminder) {
        if (!iso) throw new Error("Pick a date and time for the reminder.");
        await runTool("reminder_add", { title: title.trim(), remind_at: iso });
      } else await runTool("task_add", { title: title.trim(), due_at: iso });
      setTitle("");
      setAt("");
    });
  };

  const calculate = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await runTool<{ result: number }>("calculator", { expression: expr });
      setCalc(String(r.result));
      setErr("");
    } catch (er) {
      setCalc("");
      setErr(msg(er));
    }
  };

  const search = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await runTool<{ results: { path: string; snippet: string }[] }>("doc_search", { query: dq });
      setDocs(r.results);
      setErr("");
    } catch (er) {
      setDocs(null);
      setErr(msg(er));
    }
  };

  return (
    <div className="stack">
      {err && <p role="alert" className="error">{err}</p>}
      <section className="card" aria-label="Tasks and reminders">
        <h2>Tasks &amp; reminders</h2>
        <form onSubmit={add} className="row">
          <input aria-label="Task title" placeholder="What needs doing?" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
          <input aria-label="Date and time" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} style={{ flex: "none", width: "auto" }} />
          <label className="row">
            <input type="checkbox" style={{ width: "auto", margin: 0 }} checked={asReminder} onChange={(e) => setAsReminder(e.target.checked)} />
            Reminder
          </label>
          <button type="submit" disabled={!title.trim()}>Add</button>
        </form>
        <p className="muted">Reminders appear in OMNI while it is open; OMNI cannot notify you when the app is closed.</p>
        <ul className="plain">
          {tasks.map((t) => (
            <li key={t.id} className={t.done ? "off" : ""}>
              <span className="tag">{t.remind_at ? "reminder" : "task"}</span> {t.title}
              <span className="muted"> {when(t.remind_at ?? t.due_at)}</span>
              <span className="spacer" />
              {!t.done && (
                <button className="link small" onClick={() => void act(() => runTool("task_complete", { id: t.id }))}>Done</button>
              )}
              <button
                className="link small"
                onClick={() => window.confirm("Delete this permanently?") && void act(() => runTool("task_delete", { id: t.id }, true))}
              >
                Delete
              </button>
            </li>
          ))}
          {tasks.length === 0 && <li className="muted">Nothing here yet.</li>}
        </ul>
      </section>

      <section className="card" aria-label="Calculator">
        <h2>Calculator</h2>
        <form onSubmit={(e) => void calculate(e)} className="row">
          <input aria-label="Expression" placeholder="e.g. (12.5*4)+sqrt(81)" value={expr} maxLength={200} onChange={(e) => setExpr(e.target.value)} />
          <button type="submit" disabled={!expr.trim()}>=</button>
        </form>
        {calc && <p className="ok" role="status">{calc}</p>}
      </section>

      <section className="card" aria-label="Documents">
        <h2>Documents</h2>
        <form onSubmit={(e) => void search(e)} className="row">
          <input aria-label="Search documents" placeholder="Search your authorized documents folder" value={dq} maxLength={200} onChange={(e) => setDq(e.target.value)} />
          <button type="submit" disabled={!dq.trim()}>Search</button>
        </form>
        {docs && (
          <ul className="plain">
            {docs.map((d) => (
              <li key={d.path} style={{ display: "block" }}>
                <strong>{d.path}</strong>
                <div className="muted">…{d.snippet}…</div>
              </li>
            ))}
            {docs.length === 0 && <li className="muted">No matches.</li>}
          </ul>
        )}
      </section>
    </div>
  );
}
