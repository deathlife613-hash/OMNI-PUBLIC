import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError, activateSkill, draftSkill, listSkills, proposeSkill, rejectSkill, reviewSkill, rollbackSkill, runSkill, skillAction,
  type Skill, type SkillVersion,
} from "./api";

const msg = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");
const permText = (p: SkillVersion["manifest"]["permissions"]) =>
  [p.use_memories && "reads your saved memories", p.network && "network", p.files && "files"].filter(Boolean).join(", ") || "none (text in, text out)";

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [ask, setAsk] = useState("");
  const [json, setJson] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [runIn, setRunIn] = useState<Record<string, string>>({});
  const [out, setOut] = useState<Record<string, string>>({});

  const load = useCallback(() => { listSkills().then(setSkills, (e) => setErr(msg(e))); }, []);
  useEffect(load, [load]);

  const act = async (fn: () => Promise<unknown>, ok = "") => {
    setErr(""); setNote("");
    try { await fn(); if (ok) setNote(ok); } catch (e) { setErr(msg(e)); }
    load();
  };

  const activate = (n: string, v: SkillVersion) =>
    act(async () => {
      if (!window.confirm(`Activate ${n}@${v.version}?\nPermissions: ${permText(v.manifest.permissions)}\nIt will be able to run when you ask.`)) return;
      try { await activateSkill(n, v.version); }
      catch (e) {
        if (e instanceof ApiError && e.kind === "permission_change" && window.confirm(`${e.message}\n\nAccept the extra permissions?`)) await activateSkill(n, v.version, true);
        else throw e;
      }
    }, "Activated.");

  const propose = (e: FormEvent) => {
    e.preventDefault();
    void act(async () => { await proposeSkill(JSON.parse(json)); setJson(""); }, "Staged for review (inactive until you approve).");
  };

  return (
    <div className="stack">
      {err && <p role="alert" className="error">{err}</p>}
      {note && <p role="status" className="ok">{note}</p>}
      <section className="card" aria-label="New skill">
        <h2>Skills</h2>
        <p className="muted">
          Skills are reusable prompt templates: text in, text out. They contain no code and cannot use files, the network or tools. New skills are inactive until you review and approve them.
        </p>
        <form className="row" onSubmit={(e) => { e.preventDefault(); void act(async () => { await draftSkill(ask); setAsk(""); }, "Drafted into staging (inactive)."); }}>
          <input aria-label="Describe a skill" placeholder="Ask the Skill Creator, e.g. 'turn messy notes into bullets'" value={ask} maxLength={1000} onChange={(e) => setAsk(e.target.value)} />
          <button type="submit" disabled={ask.trim().length < 5}>Draft</button>
        </form>
        <form onSubmit={propose}>
          <textarea aria-label="Skill manifest JSON" rows={4} style={{ width: "100%" }} placeholder="…or paste a manifest (JSON)" value={json} onChange={(e) => setJson(e.target.value)} />
          <button type="submit" disabled={!json.trim()}>Stage manifest</button>
        </form>
      </section>

      {skills.map((s) => (
        <section className="card" key={s.name} aria-label={`Skill ${s.name}`}>
          <h2>{s.name} <span className="tag">{s.enabled ? `active ${s.active_version}` : s.active_version ? "disabled" : "not approved"}</span></h2>
          {s.versions.map((v) => (
            <div key={v.version} style={{ borderTop: "1px solid var(--line)", paddingTop: 8, marginTop: 8 }}>
              <strong>v{v.version}</strong> <span className="tag">{v.status}</span> <span className="muted">by {v.created_by}</span>
              <p>{v.manifest.description}</p>
              <p className="muted">Trigger: {v.manifest.trigger} · Permissions: {permText(v.manifest.permissions)}</p>
              <p className={v.validation.ok ? "ok" : "error"}>{v.validation.ok ? `Validation passed; ${v.validation.tests.length} test(s) passed.` : `Validation failed: ${[...v.validation.errors, ...v.validation.tests.filter((t) => !t.passed).map((t) => `test ${t.test}: ${t.detail}`)].join(" · ")}`}</p>
              {v.validation.warnings.length > 0 && <p className="muted">Warnings: {v.validation.warnings.join(" · ")}</p>}
              {v.review && <pre className="diff">{v.review}</pre>}
              <div className="row">
                {(v.status === "staged" || v.status === "superseded") && v.validation.ok && <button onClick={() => void activate(s.name, v)}>Approve &amp; activate</button>}
                {v.status === "staged" && <button onClick={() => void act(() => reviewSkill(s.name, v.version))}>AI review (advisory)</button>}
                {v.status === "staged" && <button onClick={() => void act(() => rejectSkill(s.name, v.version))}>Reject</button>}
              </div>
            </div>
          ))}
          {s.active_version && (
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={() => void act(() => skillAction(s.name, s.enabled ? "disable" : "enable"))}>{s.enabled ? "Disable" : "Enable"}</button>
              <button onClick={() => window.confirm("Roll back to the previous version?") && void act(() => rollbackSkill(s.name), "Rolled back.")}>Roll back</button>
            </div>
          )}
          {s.enabled && s.active_version && (() => {
            const m = s.versions.find((v) => v.version === s.active_version)?.manifest;
            return (
              <form className="row" onSubmit={(e) => { e.preventDefault(); void act(async () => { const r = await runSkill(s.name, runIn); setOut({ ...out, [s.name]: r.output }); }); }}>
                {m?.inputs.map((i) => (
                  <input key={i.name} aria-label={`${s.name} ${i.name}`} placeholder={i.name} value={runIn[i.name] ?? ""} onChange={(e) => setRunIn({ ...runIn, [i.name]: e.target.value })} />
                ))}
                <button type="submit">Run</button>
                {out[s.name] && <pre className="diff" style={{ width: "100%" }}>{out[s.name]}</pre>}
              </form>
            );
          })()}
        </section>
      ))}
      {skills.length === 0 && <p className="muted">No skills yet.</p>}
    </div>
  );
}
