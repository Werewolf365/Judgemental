"use client";
import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";

/** Top-K uncertainty view for the edge-case Bayesian scoring model.
 *  Plain language throughout: rank, score, likely range, Top-K chance,
 *  High/Medium/Low confidence, close competitors ("A is 72% likely to rank
 *  above B"), flags with extra-judging recommendations. Organizer/admin only
 *  server-side; this component only mirrors that for usability. */
export default function UncertaintyPanel({ eventId, onChanged }: { eventId: string; onChanged?: () => void }) {
  const [data, setData] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [roster, setRoster] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [swapReason, setSwapReason] = useState("");
  const [assignSel, setAssignSel] = useState<Record<string, string>>({});

  async function load() {
    setMsg("");
    try {
      setData(await api(`/events/${eventId}/bayes/results`).catch(() => null));
      setRuns((await api(`/events/${eventId}/bayes/runs`).catch(() => ({ runs: [] }))).runs || []);
      setRoster(((await api(`/events/${eventId}/judges`).catch(() => ({ judges: [] }))).judges || [])
        .filter((j: any) => j.is_active && j.role === "JUDGE"));
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { if (eventId) load(); }, [eventId]);

  async function calculate() {
    if (!confirm("Run the Bayesian scoring calculation? Use this when each project has only one judge and the pairwise ranking cannot run. Recalculating after extra judging creates a new version — history is kept.")) return;
    setMsg(""); setBusy(true);
    try {
      const d = await api(`/events/${eventId}/bayes/calculate`, { method: "POST", body: "{}" });
      setMsg(`Scored ${d.projects} projects from ${d.observations} evaluation(s).`);
      await load();
      onChanged?.();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  const confBadge = (c: string) =>
    c === "High" ? "badge-ok" : c === "Medium" ? "badge-track" : "badge-muted";

  async function swapPair(a: string, b: string, an: string, bn: string) {
    if (!confirm(`Interchange the ranks of “${an}” and “${bn}”? The model ranking underneath is kept — this records your decision on top of it.`)) return;
    setMsg(""); setBusy(true);
    try {
      await api(`/events/${eventId}/bayes/swap`, { method: "POST",
        body: JSON.stringify({ project_a_id: a, project_b_id: b, reason: swapReason.trim() || null }) });
      setSwapReason("");
      setMsg("Ranks interchanged — your decision is recorded and shown below.");
      await load();
      onChanged?.();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  async function revert() {
    if (!confirm("Drop your manual rank decision and go back to the model ranking?")) return;
    setMsg(""); setBusy(true);
    try {
      await api(`/events/${eventId}/bayes/overrides`, { method: "DELETE" });
      setMsg("Back to the model ranking.");
      await load();
      onChanged?.();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  async function assignJudge(projectId: string, title: string) {
    const judgeId = assignSel[projectId];
    if (!judgeId) { setMsg("Pick a judge from the existing pool first."); return; }
    const j = roster.find((r: any) => r.user_id === judgeId);
    if (!confirm(`Assign ${j?.display_name || "this judge"} to “${title}” for extra judging? (Judging must be open — reopen the window first if it is closed.)`)) return;
    setMsg(""); setBusy(true);
    try {
      await api(`/events/${eventId}/assignments/manual`, { method: "POST",
        body: JSON.stringify({ project_id: projectId, judge_user_id: judgeId }) });
      setMsg(`Assigned — they can now score “${title}”. Recalculate after they submit.`);
      await load();
      onChanged?.();
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  const shown = data?.effective?.length ? data.effective : (data?.ranking || []);
  // Assign-a-judge appears ONLY on projects the model recommends re-evaluating
  // (members of a close call), not on settled rows.
  const reevaluate = new Set<string>();
  for (const c of data?.close_calls || []) {
    if (c.project_a_id) reevaluate.add(c.project_a_id);
    if (c.project_b_id) reevaluate.add(c.project_b_id);
  }

  return (
    <div>
      <p style={{ color: "var(--muted)" }}>
        For events where each project has only one judge, the pairwise ranking cannot run.
        This model adjusts for strict and generous judges and shows how certain each position is.
        A Low-confidence position may change with more judging.
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
        <button className="btn" disabled={busy} onClick={calculate}>Calculate scores + uncertainty</button>
        <button className="btn-ghost btn-sm" style={{ alignSelf: "center" }} onClick={load}>Refresh</button>
      </div>
      {msg && <p>{msg}</p>}
      {data?.notice && (
        <div className="deadline-bar" style={{ marginBottom: 12 }}><span>{data.notice}</span></div>
      )}
      {data?.flags?.message && (
        <div className="deadline-bar" style={{ marginBottom: 12 }} role="status"><b>⚠ {data.flags.message}</b></div>
      )}
      {data ? (
        <div>
          <h2>Top {data.top_k} <span style={{ fontWeight: 400, fontSize: 13, color: "var(--muted)" }}>
            run {data.run.id} · {fmtDate(data.run.finished_at)}</span></h2>
          {data.has_manual_overrides && (
            <div className="deadline-bar" style={{ marginBottom: 8 }} role="status">
              <span>You adjusted this ranking — <b>manual</b> badges mark your decisions, the model order is kept underneath.</span>
              <span style={{ marginLeft: 8 }}><button className="link-btn" disabled={busy} onClick={revert}>Revert to model ranking</button></span>
            </div>
          )}
          {shown.map((r: any) => (
            <div key={r.project_id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                <span className="badge badge-track">#{r.effective_rank ?? r.rank}</span>
                {r.rank_source === "manual" && <span className="badge badge-muted">manual</span>}
                <b>{r.title}</b><span style={{ color: "var(--muted)" }}>{r.team} · {r.track}</span>
                <span style={{ marginLeft: "auto", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <span className="mono">score {Number(r.score).toFixed(2)}</span>
                  <span style={{ fontSize: 13, color: "var(--muted)" }}>
                    likely {Number(r.likely_range[0]).toFixed(1)}–{Number(r.likely_range[1]).toFixed(1)}</span>
                  <span style={{ fontSize: 13 }}>Top {data.top_k}: <b>{Math.round(r.p_top * 100)}%</b></span>
                  <span className={`badge ${confBadge(r.confidence)}`}>{r.confidence}</span>
                </span>
              </div>
              <div style={{ fontSize: 13.5, color: "var(--muted)", marginTop: 4 }}>{r.summary}</div>
              {reevaluate.has(r.project_id) && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
                  <span className="badge badge-muted">needs re-evaluation</span>
                  <select aria-label={`Assign a judge to ${r.title}`} value={assignSel[r.project_id] || ""}
                    onChange={(e) => setAssignSel({ ...assignSel, [r.project_id]: e.target.value })}>
                    <option value="">Assign a judge from the pool…</option>
                    {roster.map((j: any) => (
                      <option key={j.user_id} value={j.user_id}>
                        {j.display_name} — load {j.active_load}, done {j.completed}
                      </option>
                    ))}
                  </select>
                  <button className="btn-ghost btn-sm" disabled={busy} onClick={() => assignJudge(r.project_id, r.title)}>
                    Assign</button>
                </div>
              )}
            </div>
          ))}
          {!!data.close_calls?.length && (
            <div style={{ marginTop: 12 }}>
              <h3>Close calls — where extra judging helps most</h3>
              <div style={{ marginBottom: 8 }}>
                <label htmlFor="swap-reason">Reason for a rank decision (optional, stored with it)</label>
                <input id="swap-reason" value={swapReason} onChange={(e) => setSwapReason(e.target.value)}
                  placeholder="e.g. demo impressed the room — see notes" maxLength={500} />
              </div>
              {data.close_calls.map((c: any, i: number) => (
                <div key={i} style={{ padding: "8px 0", borderTop: "1px solid var(--line)", fontSize: 14 }}>
                  <b>{c.plain}</b>
                  <div style={{ color: "var(--muted)", fontSize: 13.5 }}>{c.reason}</div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
                    <button className="btn-ghost btn-sm" disabled={busy}
                      onClick={() => swapPair(c.project_a_id, c.project_b_id, c.project_a, c.project_b)}>
                      Interchange these two ranks</button>
                    {c.suggested_judge?.user_id && (
                      <span style={{ fontSize: 13.5, color: "var(--muted)" }}>Suggested judge: <b>{c.suggested_judge.display_name}</b>
                        {" "}— or pick any pool judge on the project rows above.</span>
                    )}
                  </div>
                </div>
              ))}
              <p className="form-note">Reopen the judging window, assign the suggested judge to the project,
                then run “Calculate scores + uncertainty” again for an updated ranking.</p>
            </div>
          )}
          {!!data.judges?.length && (
            <div style={{ marginTop: 12 }}>
              <h3>Judge adjustments</h3>
              {data.judges.map((j: any) => (
                <div key={j.user_id} style={{ display: "flex", gap: 10, padding: "6px 0", borderTop: "1px solid var(--line)", fontSize: 14 }}>
                  <b>{j.display_name}</b>
                  <span style={{ marginLeft: "auto", color: "var(--muted)" }}>
                    {j.n_evaluations} evaluation(s) · {j.plain}</span>
                </div>
              ))}
            </div>
          )}
          {!!runs.length && (
            <div style={{ marginTop: 12 }}><h3>Run history</h3>
              {runs.map((r: any) => (
                <div key={r.id} style={{ fontSize: 13.5, color: "var(--muted)" }}>
                  <span className="mono">{r.id}</span> · {r.status} · {r.n_projects} projects · {r.n_judges} judges · {r.n_observations} evaluation(s) · {fmtDate(r.finished_at || r.started_at)}
                  {r.error && <span> · error: {r.error}</span>}
                </div>
              ))}</div>
          )}
        </div>
      ) : (
        <div className="empty"><h3>No Bayesian scoring yet</h3>
          <p>Close the judging deadline, then calculate. Recalculating after extra judging never rewrites history.</p></div>
      )}
    </div>
  );
}
