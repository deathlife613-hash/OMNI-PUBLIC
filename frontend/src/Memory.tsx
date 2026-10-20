import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  createMemory,
  createNote,
  deleteMemory,
  deleteNote,
  exportAll,
  getMemorySettings,
  listMemories,
  listNotes,
  patchMemory,
  patchNote,
  putMemorySettings,
  restoreBackup,
  type Memory,
  type Note,
} from "./api";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

export default function MemoryCenter() {
  const [mems, setMems] = useState<Memory[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [q, setQ] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [newMem, setNewMem] = useState("");
  const [kind, setKind] = useState<Memory["kind"]>("fact");
  const [nTitle, setNTitle] = useState("");
  const [nBody, setNBody] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, n, s] = await Promise.all([listMemories(q), listNotes(q), getMemorySettings()]);
      setMems(m);
      setNotes(n);
      setEnabled(s.enabled);
      setErr("");
    } catch (e) {
      setErr(msg(e));
    }
  }, [q]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await load();
    } catch (e) {
      setErr(msg(e));
    }
  };

  const addMem = (e: FormEvent) => {
    e.preventDefault();
    if (!newMem.trim()) return;
    void run(async () => {
      await createMemory(newMem.trim(), kind);
      setNewMem("");
    });
  };

  const addNote = (e: FormEvent) => {
    e.preventDefault();
    if (!nTitle.trim()) return;
    void run(async () => {
      await createNote(nTitle.trim(), nBody);
      setNTitle("");
      setNBody("");
    });
  };

  const download = async () => {
    try {
      const data = await exportAll();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `omni-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      setNote("Backup downloaded.");
    } catch (e) {
      setErr(msg(e));
    }
  };

  const restore = async (file: File | undefined) => {
    if (!file) return;
    if (!window.confirm("Restore REPLACES all current conversations, memories and notes with this file. Continue?")) return;
    try {
      const r = await restoreBackup(JSON.parse(await file.text()));
      setNote(`Restored ${Object.entries(r.restored).map(([k, v]) => `${v} ${k}`).join(", ")}.`);
      await load();
    } catch (e) {
      setErr(e instanceof SyntaxError ? "That file is not valid JSON." : msg(e));
    }
  };

  return (
    <div className="stack">
      <section className="card" aria-label="Memory settings">
        <h2>Memory</h2>
        <label className="row">
          <input
            type="checkbox"
            style={{ width: "auto", margin: 0 }}
            checked={enabled}
            onChange={(e) => void run(() => putMemorySettings(e.target.checked))}
          />
          Let OMNI use my saved memories in chats
        </label>
        <p className="muted">OMNI only uses memories you added or approved. Passwords and API keys are refused.</p>
        <input aria-label="Search memories and notes" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="row">
          <button onClick={() => void download()}>Download backup</button>
          <label className="filebtn">
            Restore backup…
            <input type="file" accept="application/json" hidden onChange={(e) => void restore(e.target.files?.[0])} />
          </label>
        </div>
        {note && <p role="status" className="ok">{note}</p>}
        {err && <p role="alert" className="error">{err}</p>}
      </section>

      <section className="card" aria-label="Memories">
        <h2>Saved memories</h2>
        <form onSubmit={addMem} className="row">
          <input aria-label="New memory" placeholder="e.g. I prefer short answers" value={newMem} maxLength={500} onChange={(e) => setNewMem(e.target.value)} />
          <select aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value as Memory["kind"])}>
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
          </select>
          <button type="submit" disabled={!newMem.trim()}>Add</button>
        </form>
        <ul className="plain">
          {mems.map((m) => (
            <li key={m.id} className={m.enabled ? "" : "off"}>
              <span className="tag">{m.kind}</span> {m.content}
              <span className="spacer" />
              <button className="link small" onClick={() => void run(() => patchMemory(m.id, { enabled: !m.enabled }))}>
                {m.enabled ? "Disable" : "Enable"}
              </button>
              <button
                className="link small"
                onClick={() => {
                  const v = window.prompt("Edit memory", m.content);
                  if (v && v.trim()) void run(() => patchMemory(m.id, { content: v.trim() }));
                }}
              >
                Edit
              </button>
              <button
                className="link small"
                onClick={() => window.confirm("Delete this memory?") && void run(() => deleteMemory(m.id))}
              >
                Delete
              </button>
            </li>
          ))}
          {mems.length === 0 && <li className="muted">{q ? "No matches." : "Nothing saved yet."}</li>}
        </ul>
      </section>

      <section className="card" aria-label="Notes">
        <h2>Notes</h2>
        <form onSubmit={addNote}>
          <input aria-label="Note title" placeholder="Title" value={nTitle} maxLength={120} onChange={(e) => setNTitle(e.target.value)} />
          <textarea aria-label="Note body" rows={3} placeholder="Write a note…" value={nBody} onChange={(e) => setNBody(e.target.value)} style={{ width: "100%" }} />
          <button type="submit" disabled={!nTitle.trim()}>Save note</button>
        </form>
        <ul className="plain">
          {notes.map((n) => (
            <li key={n.id} style={{ display: "block" }}>
              <strong>{n.title}</strong>
              <div className="muted" style={{ whiteSpace: "pre-wrap" }}>{n.body}</div>
              <button
                className="link small"
                onClick={() => {
                  const v = window.prompt("Edit note", n.body);
                  if (v !== null) void run(() => patchNote(n.id, { body: v }));
                }}
              >
                Edit
              </button>
              <button className="link small" onClick={() => window.confirm("Delete this note?") && void run(() => deleteNote(n.id))}>
                Delete
              </button>
            </li>
          ))}
          {notes.length === 0 && <li className="muted">{q ? "No matches." : "No notes yet."}</li>}
        </ul>
      </section>
    </div>
  );
}
