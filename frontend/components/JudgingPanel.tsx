"use client";
import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { I } from "@/components/art";
import DateTimePicker from "@/components/DateTimePicker";
import Popup from "@/components/Popup";
import UncertaintyPanel from "@/components/UncertaintyPanel";

type Tab = "rubric" | "judges" | "settings" | "results" | "uncertainty";

/** Organizer judging console: rubric builder, judge roster with load,
 *  judging settings, and results. Rendered for the console's working event.
 *  Everything here is organizer/admin-only server-side; this panel only
 *  mirrors those permissions for usability. */
export default function JudgingPanel({ eventId }: { eventId: string }) {
  const [tab, setTab] = useState<Tab>("rubric");
  const [status, setStatus] = useState<any>(null);
  const [rubric, setRubric] = useState<any[]>([]);
  const [judges, setJudges] = useState<any[]>([]);
  const [balance, setBalance] = useState<any>(null);
  const [results, setResults] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [settingsSaved, setSettingsSaved] = useState("");
  // Final-score blend (UI only for now): whether crowd votes count and at
  // what weight. Stored per event in this browser; the math wires up later.
  const loadBlend = (id: string) => {
    try {
      const p = JSON.parse(localStorage.getItem(`blend:${id}`) || "");
      if (p && typeof p.crowdPct === "number")
        return { enabled: !!p.enabled, crowdPct: Math.min(100, Math.max(0, Math.round(p.crowdPct))) };
    } catch { /* fresh defaults */ }
    return { enabled: false, crowdPct: 30 };
  };
  const [blend, setBlend] = useState(loadBlend(eventId));
  const [crowd, setCrowd] = useState<any[]>([]);
  const [votingOn, setVotingOn] = useState(false);
  useEffect(() => {
    setBlend(loadBlend(eventId));
    api(`/events/${eventId}/voting/standings`).then((s) => setCrowd(s?.ranking || [])).catch(() => setCrowd([]));
    api(`/events/${eventId}/voting`).then((v) => setVotingOn(!!v?.config?.voting_enabled)).catch(() => setVotingOn(false));
  }, [eventId]);
  function saveBlend(patch: Partial<{ enabled: boolean; crowdPct: number }>) {
    setBlend((b) => {
      const n = { ...b, ...patch };
      try { localStorage.setItem(`blend:${eventId}`, JSON.stringify(n)); } catch { /* private mode */ }
      return n;
    });
  }
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ title: string; body: React.ReactNode } | null>(null);

  // rubric form
  const [cName, setCName] = useState("");
  const [cDesc, setCDesc] = useState("");
  const [cWeight, setCWeight] = useState("");
  const [cLo, setCLo] = useState("");
  const [cHi, setCHi] = useState("");
  const [editing, setEditing] = useState<any>(null);
  // judges form
  const [jEmail, setJEmail] = useState("");
  // settings form
  const [sOpen, setSOpen] = useState("");
  const [sClose, setSClose] = useState("");
  const [sPer, setSPer] = useState(2);
  const [sRolling, setSRolling] = useState(true);

  async function load() {
    setMsg("");
    try {
      const st = await api(`/events/${eventId}/judging`);
      setStatus(st);
      setSOpen(st.config.judging_open ? st.config.judging_open.slice(0, 16) : "");
      setSClose(st.config.judging_close ? st.config.judging_close.slice(0, 16) : "");
      setSPer(st.config.judges_per_project);
      setSRolling(st.config.rolling_judging);
      setRubric((await api(`/events/${eventId}/rubric`).catch(() => ({ criteria: [] }))).criteria || []);
      const roster = await api(`/events/${eventId}/judges`).catch(() => ({ judges: [] }));
      setJudges(roster.judges || []);
      setBalance(roster.balance || null);
      const r = await api(`/events/${eventId}/results`).catch(() => null);
      setResults(r);
      setRuns((await api(`/events/${eventId}/results/runs`).catch(() => ({ runs: [] }))).runs || []);
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { if (eventId) load(); }, [eventId]);

  async function addCriterion(e: React.FormEvent) {
    e.preventDefault(); setMsg(""); setBusy(true);
    try {
      const body: any = { name: cName.trim(), description: cDesc.trim() || null, display_order: rubric.length };
      if (cWeight.trim() !== "") body.weight = Number(cWeight);
      if (cLo.trim() !== "" || cHi.trim() !== "") {
        const lo = cLo.trim() === "" ? 0 : Number(cLo);
        const hi = cHi.trim() === "" ? 10 : Number(cHi);
        if (!(hi > lo)) { setMsg("Scale max must be greater than scale min."); return; }
        body.score_lo = lo; body.score_hi = hi;
      }
      const stop = capCheck(null, body.weight ?? null);
      if (stop) { setMsg(stop); return; }
      await api(`/events/${eventId}/rubric`, { method: "POST", body: JSON.stringify(body) });
      setCName(""); setCDesc(""); setCWeight(""); setCLo(""); setCHi("");
      await load();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }
  async function saveEdit() {
    if (!editing) return;
    setMsg(""); setBusy(true);
    try {
      const body: any = { name: editing.name.trim(), description: editing.description || null,
        display_order: editing.display_order ?? 0 };
      if (editing.weight === "" || editing.weight == null) body.weight = null;
      else body.weight = Number(editing.weight);
      const elo = editing.score_lo === "" || editing.score_lo == null ? null : Number(editing.score_lo);
      const ehi = editing.score_hi === "" || editing.score_hi == null ? null : Number(editing.score_hi);
      if ((elo != null || ehi != null) && !((ehi ?? 10) > (elo ?? 0))) {
        setMsg("Scale max must be greater than scale min."); return;
      }
      body.score_lo = elo; body.score_hi = ehi;
      const stop = capCheck(editing.id, body.weight);
      if (stop) { setMsg(stop); return; }
      await api(`/rubric/${editing.id}`, { method: "PATCH", body: JSON.stringify(body) });
      setEditing(null);
      await load();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }
  async function removeCriterion(c: any) {
    const word = status?.rubric_locked ? "deactivate (judging has started — history is preserved)" : "delete it";
    if (!confirm(`Remove “${c.name}”? This will ${word}.`)) return;
    setMsg("");
    try {
      const d = await api(`/rubric/${c.id}`, { method: "DELETE" });
      setMsg(d.deactivated ? `“${c.name}” deactivated — past scores keep their meaning.` : `“${c.name}” removed.`);
      await load();
    } catch (e: any) { setMsg(e.message); }
  }
  async function addJudge(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!jEmail.trim()) { setMsg("Enter the judge's email."); return; }
    try {
      const d = await api(`/events/${eventId}/judges`, { method: "POST", body: JSON.stringify({ email: jEmail.trim() }) });
      setJEmail("");
      setMsg(`${d.judge.display_name} can now judge this event.`);
      await load();
    } catch (e: any) { setMsg(e.message); }
  }
  async function removeJudge(j: any) {
    if (!confirm(`Remove ${j.display_name} from the judging roster? Incomplete work is reassigned; submitted scores are kept.`)) return;
    setMsg("");
    try {
      const d = await api(`/events/${eventId}/judges/${j.user_id}`, { method: "DELETE" });
      setMsg(`Removed — ${d.revoked} assignment(s) revoked, ${d.refilled} refilled.`);
      await load();
    } catch (e: any) { setMsg(e.message); }
  }
  async function batch() {
    setMsg(""); setBusy(true);
    try {
      const d = await api(`/events/${eventId}/assignments/batch`, { method: "POST", body: "{}" });
      setMsg(`Batch assignment: ${d.assignments_created} new assignment(s) across ${d.projects_touched} project(s).`);
      await load();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }
  async function saveSettings() {
    setMsg(""); setSettingsSaved(""); setBusy(true);
    try {
      await api(`/events/${eventId}/judging`, { method: "PATCH", body: JSON.stringify({
        judging_open: sOpen || null, judging_close: sClose || null,
        judges_per_project: Number(sPer), rolling_judging: sRolling,
      }) });
      setMsg("Judging settings saved.");
      setSettingsSaved(`Saved ✓ ${new Date().toLocaleTimeString()}`);
      await load();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }
  async function calculate() {
    if (!confirm("Run the final ranking calculation? It uses all submitted evaluations and cannot be edited afterwards — only recalculated as a new version.")) return;
    setMsg(""); setBusy(true);
    try {
      const d = await api(`/events/${eventId}/results/calculate`, { method: "POST", body: "{}" });
      setNotice({ title: "Ranking calculated",
        body: <>{d.projects} projects ranked from {d.comparisons} pairwise comparisons by {d.judges} judges. The full evidence trail is stored with the run.</> });
      await load();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  const stage = status?.stage || "—";
  const locked = !!status?.rubric_locked;
  const weights = rubric.filter((c) => c.is_active);
  const explicit = weights.filter((c) => c.weight != null);
  const wTotal = explicit.reduce((s, c) => s + Number(c.weight), 0);
  const wRemaining = Math.max(0, 100 - wTotal);
  const wOver = wTotal > 100 + 1e-9;
  const wShort = explicit.length === weights.length && weights.length > 0 && Math.abs(wTotal - 100) > 1e-6;
  const fmtPct = (n: number) => String(Math.round(n * 100) / 100);
  function capCheck(exceptId: string | null, w: number | null): string | null {
    if (w == null) return null;
    const others = weights.filter((c) => c.weight != null && c.id !== exceptId)
      .reduce((s, c) => s + Number(c.weight), 0);
    if (others + w > 100 + 1e-9) {
      const rem = Math.max(0, 100 - others);
      return `That would push the rubric past 100% (${fmtPct(rem)}% remaining) — lower it or trim another criterion first.`;
    }
    return null;
  }
  const autoSecs = status?.auto_assign?.every_seconds;
  const autoCadence = autoSecs == null ? "" : autoSecs >= 60 ? `${Math.round(autoSecs / 60)} min` : `${autoSecs} s`;
  const autoLast = status?.auto_assign?.last_run ? fmtDate(status.auto_assign.last_run) : null;
  const autoCreated = status?.auto_assign?.last_created ?? 0;

  return (
    <div className="card field">
      {notice && <Popup kind="ok" title={notice.title} dismissLabel="View results"
        onClose={() => { setNotice(null); setTab("results"); }}>{notice.body}</Popup>}
      <div className="tabs">
        <button className={tab === "rubric" ? "on" : ""} onClick={() => setTab("rubric")}>Rubric ({rubric.filter((c) => c.is_active).length})</button>
        <button className={tab === "judges" ? "on" : ""} onClick={() => setTab("judges")}>Judges ({judges.filter((j) => j.is_active).length})</button>
        <button className={tab === "settings" ? "on" : ""} onClick={() => setTab("settings")}>Settings</button>
        <button className={tab === "results" ? "on" : ""} onClick={() => setTab("results")}>Results</button>
        {status && (!status.models?.bt_viable || status.models?.bayes_ready) && (
          <button className={tab === "uncertainty" ? "on" : ""} onClick={() => setTab("uncertainty")}>Uncertainty</button>
        )}
        <span className={`badge ${stage === "RESULTS_READY" ? "badge-ok" : stage === "OPEN" ? "badge-track" : "badge-muted"}`}
          style={{ marginLeft: "auto", alignSelf: "center" }}>{stage.replace("_", " ")}</span>
        <button className="btn-ghost btn-sm" style={{ alignSelf: "center" }} onClick={load}>Refresh</button>
      </div>
      {msg && <p>{msg}</p>}

      {tab === "rubric" && (
        <div>
          {locked && <div className="deadline-bar" style={{ marginBottom: 12 }}><I.clock /> Rubric locked — judging has started. New criteria and edits are refused; removal deactivates instead.</div>}
          {!weights.length && <p style={{ color: "var(--muted)" }}>No criteria yet. Without any, judges see an empty rubric and nothing can be submitted.</p>}
          {explicit.length > 0 && explicit.length < weights.length && (
            <div className="form-error">Weights are mid-edit: {weights.length - explicit.length} active criterion/criteria still need a weight (or clear every weight for equal weighting). Submissions are blocked until this resolves.</div>)}
          {weights.length > 0 && (explicit.length === 0 || explicit.length === weights.length) && (
            <p className="form-note">{explicit.length === 0
              ? "No explicit weights — every criterion counts equally."
              : <>Weighted {explicit.map((c) => `${c.name} ${c.weight}%`).join(" · ")} — total <b>{fmtPct(wTotal)}% of 100%</b>
                {wShort ? ` (${fmtPct(wRemaining)}% still unassigned — scoring is blocked until the total is exactly 100%).` : " ✓"}</>}</p>)}
          {wOver && (
            <div className="form-error">Weights total {fmtPct(wTotal)}% — over the 100% cap. Scoring is blocked until the total is exactly 100%.</div>)}
          {rubric.map((c) => (
            <div key={c.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
              {editing?.id === c.id ? (
                <div className="grid grid-3" style={{ gap: 8 }}>
                  <input aria-label="Criterion name" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
                  <input aria-label="Weight percent" type="number" min={0} max={100} step={1} value={editing.weight ?? ""}
                    onChange={(e) => setEditing({ ...editing, weight: e.target.value })} placeholder="Weight %, blank = equal" />
                  <span style={{ display: "flex", gap: 8 }}>
                    <button className="btn btn-sm" disabled={busy} onClick={saveEdit}>Save</button>
                    <button className="btn-ghost btn-sm" onClick={() => setEditing(null)}>Cancel</button>
                  </span>
                  <input aria-label="Description" value={editing.description || ""} style={{ gridColumn: "1 / -1" }}
                    onChange={(e) => setEditing({ ...editing, description: e.target.value })} placeholder="Instructions for the judge" />
                  <input aria-label="Scale min" type="number" step="any" value={editing.score_lo ?? ""}
                    onChange={(e) => setEditing({ ...editing, score_lo: e.target.value })} placeholder="Scale min, blank = 0" />
                  <input aria-label="Scale max" type="number" step="any" value={editing.score_hi ?? ""}
                    onChange={(e) => setEditing({ ...editing, score_hi: e.target.value })} placeholder="Scale max, blank = 10" />
                </div>
              ) : (
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <div><b>{c.name}</b>{c.weight != null && <span style={{ color: "var(--muted)" }}> · {c.weight}%</span>}
                    {(c.score_lo !== 0 || c.score_hi !== 10) && <span style={{ color: "var(--muted)" }}> scale {c.score_lo}-{c.score_hi}</span>}
                    {c.description && <div style={{ fontSize: 13, color: "var(--muted)" }}>{c.description}</div>}</div>
                  {!c.is_active && <span className="badge badge-muted">Deactivated</span>}
                  <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                    {!locked && c.is_active && <button className="btn-ghost btn-sm" onClick={() => setEditing({ ...c })}>Edit</button>}
                    <button className="link-btn" onClick={() => removeCriterion(c)}>{locked || !c.is_active ? "Deactivate" : "Remove"}</button>
                  </span>
                </div>
              )}
            </div>
          ))}
          {!locked && (
            <form onSubmit={addCriterion} style={{ marginTop: 12 }}>
              <h3>Add a criterion</h3>
              <div className="grid grid-3" style={{ gap: 8 }}>
                <input aria-label="New criterion name" value={cName} onChange={(e) => setCName(e.target.value)} placeholder="e.g. Functionality" />
                <input aria-label="New criterion weight" type="number" min={0} max={100} step={1} value={cWeight}
                  onChange={(e) => setCWeight(e.target.value)} placeholder="Weight %, blank = equal" />
                <input aria-label="New criterion description" value={cDesc} onChange={(e) => setCDesc(e.target.value)} placeholder="Instructions for the judge" />
                <input aria-label="Scale min" type="number" step="any" value={cLo}
                  onChange={(e) => setCLo(e.target.value)} placeholder="Scale min, blank = 0" />
                <input aria-label="Scale max" type="number" step="any" value={cHi}
                  onChange={(e) => setCHi(e.target.value)} placeholder="Scale max, blank = 10" />
              </div>
              <div style={{ marginTop: 10 }}><button className="btn" type="submit" disabled={busy}>Add criterion</button></div>
            </form>
          )}
          {votingOn && (
          <div className="card field" style={{ margin: "14px 0 0" }}>
            <h3 style={{ marginTop: 0 }}>Final score blend</h3>
            <p className="form-note" style={{ marginTop: 0 }}>Decide whether crowd votes count toward the final score, and how much weight they carry against the judges.</p>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14.5 }}>
              <input type="checkbox" checked={blend.enabled} onChange={(e) => saveBlend({ enabled: e.target.checked })} style={{ width: "auto", margin: 0 }} />
              Count crowd votes in the final score
            </label>
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 8 }}>
              <label htmlFor="crowd-wt" style={{ fontSize: 14 }}>Crowd weight</label>
              <input id="crowd-wt" type="range" min={0} max={100} step={5} value={blend.crowdPct}
                onChange={(e) => saveBlend({ crowdPct: Number(e.target.value) })} style={{ flex: "1 1 160px" }} />
              <input type="number" min={0} max={100} value={blend.crowdPct} aria-label="Crowd weight percent"
                onChange={(e) => saveBlend({ crowdPct: Math.min(100, Math.max(0, Math.round(Number(e.target.value) || 0))) })}
                style={{ width: 72 }} />
              <span className="badge badge-track">Judges {100 - blend.crowdPct}% · Crowd {blend.crowdPct}%</span>
            </div>
            {crowd.length ? (
              <div style={{ marginTop: 8 }}>
                {crowd.map((r: any) => (
                  <div key={r.project_id} style={{ display: "flex", gap: 10, padding: "6px 0", borderTop: "1px solid var(--line)", fontSize: 13.5 }}>
                    <span className="badge badge-track">#{r.rank}</span>
                    <b>{r.title}</b>
                    <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{r.votes} vote{r.votes === 1 ? "" : "s"} · influence {Number(r.influence).toFixed(2)}</span>
                  </div>))}
              </div>
            ) : (
              <p className="form-note">No crowd votes to weigh yet — standings appear here once voting starts.</p>
            )}
            <p className="form-note">Saved in this browser only for now. Blending takes effect on a future calculation — changing these recalculates nothing today.</p>
          </div>
          )}
        </div>
      )}

      {tab === "judges" && (
        <div>
          <p style={{ color: "var(--muted)" }}>Only these accounts can score this event's projects. Everyone on the roster must already hold the JUDGE role — adding someone here never grants it.</p>
          <form onSubmit={addJudge} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "10px 0 4px" }}>
            <div style={{ flex: "1 1 240px" }}><label htmlFor="judge-email">Add a judge by email</label>
              <input id="judge-email" value={jEmail} onChange={(e) => setJEmail(e.target.value)} placeholder="judge@example.org" /></div>
            <button className="btn" type="submit">Add judge</button>
            <button type="button" className="btn-ghost" disabled={busy} onClick={batch} title="Assign every under-covered submitted project now (idempotent)">
              Run batch assignment</button>
          </form>
          {!status?.config.rolling_judging && status?.auto_assign?.enabled === false && (
            <p className="form-note">Rolling assignment is OFF and auto-assign is disabled — new submissions wait for you to press “Run batch assignment”.</p>)}
          {status?.auto_assign?.enabled !== false && (
            <p className="form-note">Auto-assign sweeps in the background{autoCadence ? ` every ${autoCadence}` : ""}{autoLast ? ` — last sweep ${autoLast} (${autoCreated} new)` : " — first sweep pending"}. “Run batch assignment” does the same pass right now without touching that schedule.</p>)}
          {balance?.checklist?.length > 0 && (
            <div className="deadline-bar" style={{ margin: "10px 0 4px", display: "block" }} role="status" aria-label="Assignment balance">
              <b>Assignment balance</b>
              <span style={{ fontWeight: 400 }}>
                {" "}· workload spread {balance.workload.spread} ·{" "}
                {balance.connected ? "one connected graph" : `${balance.components} disconnected components`} ·{" "}
                {balance.pairwise_capacity} potential pairwise comparisons
              </span>
              <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontWeight: 400 }}>
                {(balance.checklist || []).map((c: any) => (
                  <li key={c.key}>
                    {c.level === "ok" ? "✓ " : c.level === "warn" ? "⚠ " : "ℹ "}{c.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {judges.map((j: any) => (
            <div key={j.user_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)", alignItems: "center", flexWrap: "wrap" }}>
              <b>{j.display_name}</b><span style={{ color: "var(--muted)" }}>{j.email}</span>
              {!j.is_active && <span className="badge badge-muted">Removed</span>}
              <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}>
                load <b>{j.active_load}</b> · done <b>{j.completed}</b> · total <b>{j.total_assigned}</b>
                {j.pairwise_capacity > 0 && <> · <b>{j.pairwise_capacity}</b> comparisons</>}
              </span>
              {j.is_active && <button className="link-btn" onClick={() => removeJudge(j)}>Remove</button>}
            </div>
          ))}
          {!judges.length && <p style={{ color: "var(--muted)" }}>No judges on this event yet.</p>}
        </div>
      )}

      {tab === "settings" && (
        <div style={{ maxWidth: 560 }}>
          <h2>Judging window</h2>
          <p style={{ color: "var(--muted)" }}>Empty means “judge whenever”. Once the deadline passes, scores are refused and the final calculation unlocks.</p>
          <label>Judging opens (UTC)</label>
          <DateTimePicker value={sOpen} onChange={(v) => { setSOpen(v); setSettingsSaved(""); }} placeholder="No opening restriction" />
          <label>Judging closes (UTC)</label>
          <DateTimePicker value={sClose} onChange={(v) => { setSClose(v); setSettingsSaved(""); }} placeholder="No deadline yet" />
          <label>Judges per project (applies to future assignments)</label>
          <input type="number" min={1} max={10} value={sPer} onChange={(e) => { setSPer(Number(e.target.value)); setSettingsSaved(""); }} />
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14.5 }}>
            <input type="checkbox" checked={sRolling} onChange={(e) => { setSRolling(e.target.checked); setSettingsSaved(""); }} style={{ width: "auto", margin: 0 }} />
            Rolling assignment — assign each submission as it arrives (off = covered by the background sweep)
          </label>
          <div style={{ marginTop: 10 }}><button className="btn" disabled={busy} onClick={saveSettings}>Save judging settings</button></div>
          {settingsSaved && <p className="form-note" role="status" style={{ color: "var(--leaf-deep)", fontWeight: 700 }}>{settingsSaved} — these are the live settings.</p>}
        </div>
      )}

      {tab === "results" && (
        <div>
          <p>Status: <span className="badge badge-muted">{stage.replace("_", " ")}</span>{" "}
            {status?.counts && <span style={{ color: "var(--muted)", fontSize: 14 }}>
              {status.counts.evaluations_submitted} submitted evaluation(s) · {status.counts.assignments} assignment(s)</span>}</p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
            <button className="btn" disabled={busy || stage === "OPEN" || stage === "NOT_STARTED"} onClick={calculate}
              title={stage === "OPEN" || stage === "NOT_STARTED" ? "Available once the judging deadline passes" : "Run the Crowd-BT ranking"}>
              Calculate final ranking <I.arrow /></button>
            <a className="btn-ghost" href={`/api/export.csv?event_id=${eventId}`} download
              title="One row per evaluation at any stage: project, team + leader, judge, every criterion score with weight and normalized share, totals, and ranks once calculated">
              Export CSV</a>
            {(stage === "OPEN" || stage === "NOT_STARTED") && (
              <span className="form-note" style={{ alignSelf: "center" }}>Set a judging deadline under Settings — calculation unlocks after it passes. The CSV works at every stage.</span>)}
          </div>
          {results ? (
            <div>
              <h2>Final ranking <span style={{ fontWeight: 400, fontSize: 13, color: "var(--muted)" }}>
                run {results.run.id} · {results.run.n_comparisons} comparisons · {fmtDate(results.run.finished_at)}</span></h2>
              {results.ranking.map((r: any) => (
                <div key={r.project_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)", alignItems: "center" }}>
                  <span className="badge badge-track">#{r.rank}</span>
                  <b>{r.title}</b><span style={{ color: "var(--muted)" }}>{r.team} · {r.track}</span>
                  <span className="mono" style={{ marginLeft: "auto" }}>θ {Number(r.theta).toFixed(3)}</span>
                </div>
              ))}
              <h2 style={{ marginTop: 16 }}>Judge reliability</h2>
              {results.judges.map((j: any) => (
                <div key={j.user_id} style={{ display: "flex", gap: 10, padding: "6px 0", borderTop: "1px solid var(--line)", fontSize: 14 }}>
                  <b>{j.display_name}</b>
                  <span style={{ marginLeft: "auto", color: "var(--muted)" }}>
                    r = <b style={{ color: "var(--ink)" }}>{Number(j.reliability).toFixed(3)}</b> · prior {j.prior_mu} (σ {j.prior_sigma})</span>
                </div>
              ))}
              {!!runs.length && (
                <div style={{ marginTop: 12 }}><h3>Run history</h3>
                  {runs.map((r: any) => (
                    <div key={r.id} style={{ fontSize: 13.5, color: "var(--muted)" }}>
                      <span className="mono">{r.id}</span> · {r.status} · {r.n_projects} projects · {r.n_judges} judges · {r.n_comparisons} comparisons · {fmtDate(r.finished_at || r.started_at)}
                      {r.error && <span> · error: {r.error}</span>}
                    </div>
                  ))}</div>
              )}
            </div>
          ) : (
            <div className="empty"><h3>No ranking yet</h3>
              <p>Close the judging deadline, then calculate. Every version is kept — recalculating never rewrites history.</p></div>
          )}
        </div>
      )}

      {tab === "uncertainty" && status && (!status.models?.bt_viable || status.models?.bayes_ready) && (
        <UncertaintyPanel eventId={eventId} onChanged={load} />
      )}
    </div>
  );
}
