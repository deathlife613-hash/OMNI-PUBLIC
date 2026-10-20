import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  createConversation,
  deleteConversation,
  fetchModels,
  getConversation,
  listConversations,
  selectModel,
  streamMessage,
  testProvider,
  type Conversation,
  type LastTest,
  type ModelEntry,
  type Msg,
  type StreamError,
  type SystemStatus,
} from "./api";

interface Props {
  status: SystemStatus | null;
  onStatusChange: () => void;
}

export default function Chat({ status, onStatusChange }: Props) {
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState<StreamError | null>(null);
  const [models, setModels] = useState<ModelEntry[] | null>(null);
  const [test, setTest] = useState<LastTest | null>(null);
  const [info, setInfo] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  const refreshList = useCallback(async () => {
    try {
      setConvs(await listConversations());
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not load conversations.");
    }
  }, []);

  useEffect(() => {
    void refreshList();
  }, [refreshList]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, partial]);

  const open = async (id: string) => {
    setActiveId(id);
    setError(null);
    try {
      setMessages((await getConversation(id)).messages);
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not open conversation.");
    }
  };

  const newConversation = async () => {
    try {
      const c = await createConversation();
      await refreshList();
      await open(c.id);
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not create conversation.");
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this conversation and all its messages? This cannot be undone.")) return;
    try {
      await deleteConversation(id);
      if (id === activeId) {
        setActiveId(null);
        setMessages([]);
      }
      await refreshList();
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not delete.");
    }
  };

  const send = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || streaming) return;
    let id = activeId;
    if (!id) {
      try {
        id = (await createConversation()).id;
        setActiveId(id);
      } catch (err) {
        setInfo(err instanceof Error ? err.message : "Could not create conversation.");
        return;
      }
    }
    setDraft("");
    setError(null);
    setPartial("");
    setStreaming(true);
    setMessages((m) => [...m, { id: -Date.now(), role: "user", content: text, created_at: "" }]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const err = await streamMessage(id, text, (d) => setPartial((p) => p + d), ctrl.signal);
    abortRef.current = null;
    setStreaming(false);
    setPartial("");
    if (err) setError(err);
    await open(id); // reload what the server actually stored
    await refreshList();
    onStatusChange();
  };

  const runTest = async () => {
    setInfo("");
    try {
      setTest(await testProvider());
      onStatusChange();
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Test failed.");
    }
  };

  const loadModels = async () => {
    setInfo("");
    try {
      setModels((await fetchModels()).models);
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not load models.");
    }
  };

  const pick = async (model: string) => {
    try {
      await selectModel(model);
      onStatusChange();
    } catch (e) {
      setInfo(e instanceof Error ? e.message : "Could not select model.");
    }
  };

  const ai = status?.ai;
  return (
    <div className="chat">
      <aside className="card side" aria-label="Conversations">
        <button onClick={() => void newConversation()}>+ New conversation</button>
        <ul>
          {convs.map((c) => (
            <li key={c.id} className={c.id === activeId ? "active" : ""}>
              <button className="link" onClick={() => void open(c.id)}>
                {c.title}
              </button>
              <button className="x" aria-label={`Delete ${c.title}`} onClick={() => void remove(c.id)}>
                ×
              </button>
            </li>
          ))}
          {convs.length === 0 && <li className="muted">No conversations yet.</li>}
        </ul>
      </aside>

      <section className="card main" aria-label="Chat">
        <div className="provbar">
          <span>
            {ai?.provider ?? "—"} · <strong>{ai?.model ?? "no model selected"}</strong>
          </span>
          <span className="spacer" />
          <button onClick={() => void runTest()}>Test connection</button>
          <button onClick={() => void loadModels()}>Choose model</button>
          {models && (
            <select
              aria-label="Model"
              value={ai?.model ?? ""}
              onChange={(e) => void pick(e.target.value)}
            >
              <option value="" disabled>
                Select…
              </option>
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                  {m.context_window ? ` (${m.context_window.toLocaleString()} ctx)` : ""}
                </option>
              ))}
            </select>
          )}
        </div>
        {test && (
          <p role="status" className={test.ok ? "ok" : "error"}>
            {test.ok
              ? `Connected — ${test.models_available} models available (${test.latency_ms} ms).`
              : `Connection failed (${test.kind}): ${test.message}`}
          </p>
        )}
        {info && (
          <p role="alert" className="error">
            {info}
          </p>
        )}

        <div className="log" aria-live="polite">
          {messages.length === 0 && !partial && (
            <p className="muted">OMNI is online. Pick a model, then ask something.</p>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`bubble ${m.role}`}>
              <div className="who">{m.role === "user" ? "You" : "OMNI"}</div>
              <div className="text">{m.content}</div>
              {m.role === "assistant" && (
                <button className="link small" onClick={() => void navigator.clipboard?.writeText(m.content)}>
                  Copy
                </button>
              )}
            </div>
          ))}
          {partial && (
            <div className="bubble assistant">
              <div className="who">OMNI</div>
              <div className="text">{partial}</div>
            </div>
          )}
          {error && (
            <p role="alert" className="banner">
              {error.message}
              {error.kind !== "cancelled" && " Your message was saved; you can retry later."}
            </p>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={(e) => void send(e)} className="composer">
          <textarea
            aria-label="Message"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) void send(e as unknown as FormEvent);
            }}
            maxLength={8000}
            rows={2}
            placeholder="Message OMNI (Enter to send, Shift+Enter for a new line)"
          />
          {streaming ? (
            <button type="button" onClick={() => abortRef.current?.abort()}>
              Stop
            </button>
          ) : (
            <button type="submit" disabled={!draft.trim()}>
              Send
            </button>
          )}
        </form>
      </section>
    </div>
  );
}
