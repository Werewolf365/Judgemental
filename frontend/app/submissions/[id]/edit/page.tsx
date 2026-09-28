"use client";
import { useEffect, useState } from "react";
import { api, fetchMe, useCountdown } from "@/lib/api";
import { I } from "@/components/art";
import CustomAnswers from "@/components/CustomAnswers";

export default function EditSub({ params }: { params: { id: string } }) {
  const [f, setF] = useState<any>(null);
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [isCaptain, setIsCaptain] = useState<boolean | null>(null);
  const [deadline, setDeadline] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const cd = useCountdown(deadline);

  useEffect(() => {
    (async () => {
      const me = await fetchMe();
      if (!me) { window.location.href = "/login"; return; }
      try {
        const d = await api(`/submissions/${params.id}`);
        setF(d.project);
        setCustom(d.project.custom_data || {});
        try {
          const t = await api(`/teams/${d.project.team_id}`);
          const mine = (t.team?.members || []).find((m: any) => m.user_id === me.id);
          setIsCaptain(mine ? mine.role === "CAPTAIN" : false);
        } catch { setIsCaptain(false); }
        // Public endpoint hides unpublished events — fall back to the
        // authenticated one so the countdown still shows for drafts.
        try {
          const ev = await api(`/public/events/${d.project.event_id}`).catch(() => null)
            || await api(`/events/${d.project.event_id}`).then((x) => ({ event: x.event })).catch(() => null);
          if (ev?.event?.submissions_close) setDeadline(ev.event.submissions_close);
        } catch {}
      } catch (e: any) { setMsg(e.message); }
    })();
  }, [params.id]);

  async function save() {
    setBusy(true); setMsg("");
    try { const d = await api(`/submissions/${params.id}`, { method: "PATCH", body: JSON.stringify({ ...f, custom_data: custom }) }); setF(d.project); setCustom(d.project.custom_data || {}); setMsg("Draft saved."); }
    catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }
  async function remove() {
    if (!confirm("Delete this draft? This can't be undone.")) return;
    setBusy(true); setMsg("");
    try { await api(`/submissions/${params.id}`, { method: "DELETE" }); window.location.href = "/submissions"; }
    catch (e: any) { setMsg(e.message); setBusy(false); }
  }
  async function submit() {
    if (!confirm("Submit this project? It will become public and can no longer be edited.")) return;
    setBusy(true); setMsg("");
    try { const d = await api(`/submissions/${params.id}/submit`, { method: "POST", body: "{}" }); setF(d.project); setMsg("Submitted — it now appears in the public gallery."); }
    catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  if (!f) return <div className="card">{msg || "Loading editor…"}</div>;
  const closed = f.status === "SUBMITTED";
  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Editor</span><h1>{f.title || "Untitled"}</h1>
        <p><span className={`badge ${closed ? "badge-ok" : "badge-warn"}`}><span className={`pip ${closed ? "pip-green" : "pip-amber"}`} />{closed ? "Submitted" : "Draft — not public"}</span>{" "}
        {deadline && cd && !cd.past && <span className="countdown">· {cd.d}d {cd.h}h {cd.m}m left</span>}</p></div>
      {deadline && cd?.past && !closed && <div className="deadline-bar"><I.clock /> The deadline has passed — editing is locked. The server rejected further changes.</div>}
      <div className="grid grid-2" style={{ gridTemplateColumns: "2fr 1fr" }}>
        <div className="card field">
          <h2>Project identity</h2>
          <label>Title</label><input value={f.title || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <label>Summary / tagline</label><input value={f.summary || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, summary: e.target.value })} />
          <h2>Description</h2>
          <label>Full description</label><textarea value={f.description || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, description: e.target.value })} />
          <h2>Links</h2>
          <label>Repository URL</label><input value={f.repo_url || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, repo_url: e.target.value })} />
          <label>Demo URL</label><input value={f.demo_url || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, demo_url: e.target.value })} />
          <label>Live URL</label><input value={f.live_url || ""} disabled={closed || busy} onChange={(e) => setF({ ...f, live_url: e.target.value })} />
          <CustomAnswers eventId={f.event_id} value={custom} onChange={setCustom} disabled={closed || busy} />
        </div>
        <div>
          <div className="card"><h2>Publish</h2>
            <p style={{ color: "var(--muted)", fontSize: 14 }}>Drafts are private to your team. Submitting makes the project public in the gallery.</p>
            {!closed ? (<><button className="btn-ghost" onClick={save} disabled={busy} style={{ width: "100%", marginBottom: 10 }}>Save draft</button>
              {isCaptain === false
                ? <p className="form-note">Only your team captain can submit — ask them to finalize when the draft is ready.</p>
                : <button className="btn" onClick={submit} disabled={busy || isCaptain === null} style={{ width: "100%" }}>Submit project <I.arrow /></button>}
              <button className="link-btn" onClick={remove} disabled={busy} style={{ width: "100%", marginTop: 8 }}>Delete draft</button></>)
              : <p>Submitted {f.submitted_at ? new Date(f.submitted_at).toLocaleString() : ""}</p>}
            {msg && <p style={{ marginTop: 10 }}>{msg}</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
