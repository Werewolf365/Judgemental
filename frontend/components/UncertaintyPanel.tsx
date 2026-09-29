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
  const [bt, setBt] = useState<any>(null);
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
      setBt(await api(`/events/${eventId}/results`).catch(() => null));
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

  const confBadge = (c: string | null) =>
    c === "High" ? "badge-ok" : c === "Medium" || c === "Low" ? "badge-track" : "badge-muted";
  const confLabel = (c: string | null) => c || "Unknown";

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
  const topK = data ? Math.min(data.top_k, shown.length) : 0;
  // Assign-a-judge appears ONLY on projects the model recommends re-evaluating
  // (members of a close call), not on settled rows.
  const reevaluate = new Set<string>();
  for (const c of data?.close_calls || []) {
    if (c.project_a_id) reevaluate.add(c.project_a_id);
    if (c.project_b_id) reevaluate.add(c.project_b_id);
  }

  // --- Crowd-BT Laplace uncertainty, computed client-side from the stored
  // posterior (theta ± theta_std). P(A beats B) is the logistic of the gap
  // over the combined std; a pair under 90% is a close call — the same bar
  // the backend uses when it flags BT ranks.
  function pBeats(t1: number, s1: number | null, t2: number, s2: number | null): number | null {
    if (s1 == null || s2 == null) return null;
    const se = Math.sqrt(s1 * s1 + s2 * s2);
    if (!(se > 0)) return t1 > t2 ? 1 : t1 < t2 ? 0 : 0.5;
    return 1 / (1 + Math.exp(-(t1 - t2) / se));
  }
  const btRank: any[] = [...(bt?.ranking || [])].sort((a, b) => a.rank - b.rank);
  const btPairs = btRank.slice(0, -1).map((r: any, i: number) => {
    const n = btRank[i + 1];
    const p = pBeats(Number(r.theta), r.theta_std, Number(n.theta), n.theta_std);
    return { a: r, b: n, p, close: p != null && p < 0.9, unknown: p == null };
  });
  const btReevaluate = new Set<string>();
  for (const pr of btPairs) if (pr.close) { btReevaluate.add(pr.a.project_id); btReevaluate.add(pr.b.project_id); }

  // Whole-set verdict: half or more of the adjacencies undecided means the
  // ranking as a whole cannot be trusted yet.
  const btUncertain = btPairs.length > 0 && btPairs.filter((p) => p.close || p.unknown).length / btPairs.length >= 0.5;
  const byFlagged = new Set<string>([...reevaluate]);
  const byUncertain = shown.length > 1 && byFlagged.size / shown.length >= 0.5;
  const warnModels = [...(btUncertain ? ["Crowd-BT"] : []), ...(byUncertain ? ["Bayes"] : [])];

  /** One-line extra-judging control shared by both models' close-call rows. */
  function AssignRow({ projectId, title }: { projectId: string; title: string }) {
    return (
      <span style={{ display: "inline-flex", gap: 6, alignItems: "center", marginLeft: 8 }}>
        <span className="badge badge-muted">re-evaluate?</span>
        <select aria-label={`Assign a judge to ${title}`} value={assignSel[projectId] || ""}
          onChange={(e) => setAssignSel({ ...assignSel, [projectId]: e.target.value })}
          style={{ maxWidth: 190, marginBottom: 0, padding: "5px 8px", fontSize: 13 }}>
          <option value="">Pick judge…</option>
          {roster.map((j: any) => (
            <option key={j.user_id} value={j.user_id}>
              {j.display_name} (load {j.active_load})
            </option>
          ))}
        </select>
        <button className="btn-ghost btn-sm" disabled={busy} onClick={() => assignJudge(projectId, title)}>
          Assign</button>
      </span>
    );
  }

  return (
    <div>
      <p style={{ color: "var(--muted)" }}>
        For events where each project has only one judge, the pairwise ranking cannot run.
        This model adjusts for strict and generous judges and shows how certain each position is.
        A Low-confidence position may change with more judging.
      </p>
      <p className="form-note" style={{ marginTop: -6 }}>
        How to read a row: <b>score</b> is the project's estimated quality (0–10 scale); <b>likely</b> is
        where the true quality probably sits; <b>Top {topK || "…"}</b> is the chance it belongs in the top {topK || "…"}.
        High means safe to announce — anything else wants more judging on the close calls below.</p>
      {!!warnModels.length && (
        <div className="deadline-bar" style={{ marginBottom: 12 }} role="alert">
          <span><b>⚠ Too uncertain to call</b> — half or more of the {warnModels.join(" + ")} positions
            are close calls. Assign extra judges to the flagged pairs below, or blend in crowd
            voting (Rubric tab → Final score blend) before trusting this order.</span>
        </div>
      )}
      {!!btRank.length && (
        <div style={{ marginBottom: 16 }}>
          <h2>Crowd-BT uncertainty <span style={{ fontWeight: 400, fontSize: 13, color: "var(--muted)" }}>
            Laplace posterior · run {bt.run.id}</span></h2>
          {btPairs.map((pr: any, i: number) => (
            <div key={pr.a.project_id} style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className="badge badge-track">#{pr.a.rank}</span>
                <b>{pr.a.title}</b>
                <span className="mono" style={{ fontSize: 13 }}>
                  θ {Number(pr.a.theta).toFixed(2)}{pr.a.theta_std != null ? ` ± ${(1.645 * pr.a.theta_std).toFixed(2)}` : ""}</span>
                <span className={`badge ${confBadge(pr.a.confidence)}`}>{confLabel(pr.a.confidence)}</span>
                <span style={{ fontSize: 13, color: "var(--muted)" }}>
                  {pr.p == null ? "vs next: unknown" : `${Math.round(pr.p * 100)}% vs next`}</span>
                {btReevaluate.has(pr.a.project_id) && <AssignRow projectId={pr.a.project_id} title={pr.a.title} />}
              </div>
              {i === btPairs.length - 1 && (
                <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 0 0 34px", fontSize: 13.5 }}>
                  <span className="badge badge-track">#{pr.b.rank}</span>
                  <b>{pr.b.title}</b>
                  <span className="mono" style={{ fontSize: 13 }}>
                    θ {Number(pr.b.theta).toFixed(2)}{pr.b.theta_std != null ? ` ± ${(1.645 * pr.b.theta_std).toFixed(2)}` : ""}</span>
                  <span className={`badge ${confBadge(pr.b.confidence)}`}>{confLabel(pr.b.confidence)}</span>
                  {btReevaluate.has(pr.b.project_id) && <AssignRow projectId={pr.b.project_id} title={pr.b.title} />}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
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
          <h2>Top {topK} of {shown.length} <span style={{ fontWeight: 400, fontSize: 13, color: "var(--muted)" }}>
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
                  <span style={{ fontSize: 13 }}>Top {topK}: <b>{Math.round(r.p_top * 100)}%</b></span>
                  <span className={`badge ${confBadge(r.confidence)}`}>{r.confidence}</span>
                  {reevaluate.has(r.project_id) && (
                    <AssignRow projectId={r.project_id} title={r.title} />
                  )}
                </span>
              </div>
              <div style={{ fontSize: 13.5, color: "var(--muted)", marginTop: 4 }}>{r.summary}</div>
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
