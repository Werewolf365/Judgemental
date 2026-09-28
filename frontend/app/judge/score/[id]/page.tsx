"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";

/** Client mirror of the server's resolve_weights (service.py): equal split
 *  when no criterion carries a weight, normalized shares otherwise, and no
 *  total when the rubric is mid-edit (mixed). The server re-checks on
 *  submit — this is display only. */
function liveTotal(rubric: any[], scores: Record<string, number>): number | null {
  const act = (rubric || []).filter((c) => c.is_active !== false);
  if (!act.length) return null;
  const nully = act.filter((c) => c.weight == null);
  if (nully.length && nully.length !== act.length) return null;
  const w: Record<string, number> = {};
  if (!nully.length) {
    const total = act.reduce((s, c) => s + c.weight, 0);
    if (total <= 0) return null;
    for (const c of act) w[c.id] = c.weight / total;
  } else {
    for (const c of act) w[c.id] = 1 / act.length;
  }
  let t = 0;
  for (const c of act) t += (scores[c.id] ?? 0) * w[c.id];
  return t;
}

export default function ScoreProject({ params }: { params: { id: string } }) {
  const [data, setData] = useState<any>(null);
  const [scores, setScores] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);

  useEffect(() => {
    (async () => {
      if (!await fetchMe()) { window.location.href = "/login"; return; }
      try {
        const d = await api(`/judge/assignments/${params.id}`);
        setData(d.assignment);
        const ev = d.assignment.evaluation;
        if (ev) {
          const init: Record<string, string> = {};
          for (const [k, v] of Object.entries(ev.scores || {})) init[k] = String(v);
          setScores(init);
          setComment(ev.comment || "");
        }
      } catch (e: any) { setDenied(true); setMsg(e.message); }
    })();
  }, [params.id]);

  if (denied) return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
    <h1>Not available</h1><p>{msg}</p><Link href="/judge" className="btn">Back to assignments</Link></div>;
  if (!data) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;

  const a = data;
  const closed = a.status === "COMPLETED" || a.status === "REVOKED";
  const numeric: Record<string, number> = {};
  for (const [k, v] of Object.entries(scores)) {
    const n = Number(v);
    if (v !== "" && Number.isFinite(n)) numeric[k] = n;
  }
  const total = liveTotal(a.rubric || [], numeric);
  const missing = (a.rubric || []).filter((c: any) => scores[c.id] === undefined || scores[c.id] === "").length;

  async function save() {
    setBusy(true); setMsg("");
    try {
      const payload: Record<string, number> = {};
      for (const [k, v] of Object.entries(scores)) {
        if (v === "") continue;
        payload[k] = Number(v);
      }
      const d = await api(`/judge/assignments/${params.id}/scores`,
        { method: "POST", body: JSON.stringify({ scores: payload, comment }) });
      setMsg("Draft saved — only you can see it until you submit.");
      const fresh = await api(`/judge/assignments/${params.id}`);
      setData(fresh.assignment);
      void d;
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  async function submit() {
    if (!confirm("Submit these scores? They become final and feed the event ranking.")) return;
    setBusy(true); setMsg("");
    try {
      const d = await api(`/judge/assignments/${params.id}/submit`, { method: "POST", body: "{}" });
      setMsg(`Submitted — weighted total ${Number(d.weighted_score).toFixed(2)}.`);
      setData((await api(`/judge/assignments/${params.id}`)).assignment);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <Link href="/judge"><I.back /> Back to assignments</Link>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Scoring</span>
        <h1>{a.project?.title}</h1>
        <p className="lead">{a.project?.track} · by <b>{a.project?.team}</b> ·{" "}
          <span className="badge badge-muted">{a.status.replace("_", " ")}</span></p></div>
      {a.project?.summary && <div className="card"><h2>Summary</h2><p>{a.project.summary}</p>
        {a.project.description && <p style={{ whiteSpace: "pre-wrap" }}>{a.project.description}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
          {a.project.repo_url && <a className="btn-ghost btn-sm" href={a.project.repo_url} target="_blank" rel="noreferrer"><I.code /> Repository</a>}
          {a.project.demo_url && <a className="btn-ghost btn-sm" href={a.project.demo_url} target="_blank" rel="noreferrer"><I.play /> Live demo</a>}
        </div></div>}
      <div className="card field">
        <h2>Rubric</h2>
        {!a.rubric?.length && <p style={{ color: "var(--muted)" }}>The organizer has not published scoring criteria yet.</p>}
        {a.rubric?.map((c: any) => (
          <div key={c.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
            <label htmlFor={`score-${c.id}`}>{c.name}{c.weight != null ? ` (${c.weight}%)` : ""}</label>
            {c.description && <p className="form-note" style={{ marginTop: -4 }}>{c.description}</p>}
            <input id={`score-${c.id}`} type="number" min={0} max={10} step={0.5}
              value={scores[c.id] ?? ""} disabled={closed || busy}
              onChange={(e) => setScores({ ...scores, [c.id]: e.target.value })}
              placeholder="0 – 10" style={{ maxWidth: 200 }} />
          </div>
        ))}
        <label htmlFor="judge-comment">Comment <span style={{ fontWeight: 400 }}>(optional, visible to organizers)</span></label>
        <textarea id="judge-comment" value={comment} disabled={closed || busy}
          onChange={(e) => setComment(e.target.value)} placeholder="What stood out, good or bad?" />
        <div className="deadline-bar" style={{ marginBottom: 14 }}>
          <I.doc /> Weighted total: <b className="countdown">{total == null ? "—" : total.toFixed(2)}</b>
          {total == null && <span style={{ fontWeight: 400 }}>the rubric is mid-edit — scores still save, totals resume once weights are complete</span>}
          {total != null && missing > 0 && <span style={{ fontWeight: 400 }}>· {missing} criterion{missing > 1 ? "s" : ""} still unscored</span>}
        </div>
        {msg && <p>{msg}</p>}
        {!closed ? (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button className="btn-ghost" onClick={save} disabled={busy}>Save draft</button>
            <button className="btn" onClick={submit} disabled={busy}>Submit scores <I.arrow /></button>
          </div>
        ) : <p>{a.status === "COMPLETED" ? `Submitted${a.completed_at ? ` ${new Date(a.completed_at).toLocaleString()}` : ""} — final.` : "This assignment was revoked."}</p>}
      </div>
    </div>
  );
}
