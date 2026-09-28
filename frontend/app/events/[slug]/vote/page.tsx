"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";

const VOTES = 10;

function voterId(): string {
  const k = "dogfood_voter_id";
  let v = "";
  try { v = localStorage.getItem(k) || ""; } catch {}
  if (!v || !/^[0-9a-f-]{8,64}$/i.test(v)) {
    v = "xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx".replace(/x/g, () =>
      Math.floor(Math.random() * 16).toString(16));
    try { localStorage.setItem(k, v); } catch {}
  }
  return v;
}

export default function VotePage({ params }: { params: { slug: string } }) {
  const [box, setBox] = useState<any>(null);
  const [alloc, setAlloc] = useState<Record<string, number>>({});
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null);
  const [role, setRole] = useState("");
  const [turnout, setTurnout] = useState<any>(null);
  const [standings, setStandings] = useState<any[]>([]);
  const [saved, setSaved] = useState<Record<string, number>>({} as Record<string, number>);

  async function load(idEmail?: string) {
    setMsg("");
    try {
      const me = await fetchMe();
      setLoggedIn(!!me);
      setRole(me?.role || "");
      const q = new URLSearchParams();
      q.set("voter_id", voterId());  // only used in open mode; ignored otherwise
      if (idEmail) q.set("email", idEmail);
      const d = await api(`/public/events/${params.slug}/ballot?${q.toString()}`);
      setBox(d);
      setAlloc(d.my_votes || {});
      setSaved(d.my_votes || {});
      if (!d.open) {
        const r = await api(`/public/events/${params.slug}/votes/results`).catch(() => null);
        setResults(r);
      }
      if (me && (me.role === "ORGANIZER" || me.role === "ADMIN")) {
        const t = await api(`/events/${d.event.id}/voting`).catch(() => null);
        setTurnout(t?.turnout || null);
        const s = await api(`/events/${d.event.id}/voting/standings`).catch(() => null);
        setStandings(s?.ranking || []);
      }
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { load(); }, [params.slug]);

  if (!box && !msg) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;
  if (!box) return <div className="card empty"><h3>Ballot unavailable</h3><p>{msg}</p>
    <Link href={`/events/${params.slug}`}>Back to event</Link></div>;

  const mode = box.event?.voting_mode || "auth";
  const staff = role === "ORGANIZER" || role === "ADMIN";
  const used = Object.values(alloc).reduce((s: number, v: any) => s + Number(v || 0), 0);
  const left = VOTES - used;
  const savedTotal = Object.values(saved).reduce((s: number, v: any) => s + Number(v || 0), 0);
  const dirty = JSON.stringify(alloc) !== JSON.stringify(saved);

  function bump(pid: string, d: number) {
    const cur = alloc[pid] || 0;
    const next = Math.min(10, Math.max(0, cur + d));
    // Never let total allocations pass 10.
    if (d > 0 && used >= VOTES) return;
    setAlloc({ ...alloc, [pid]: next });
  }

  async function cast() {
    if (mode === "email" && !email.includes("@")) { setMsg("Enter your email to cast votes."); return; }
    if (mode === "auth" && !loggedIn) { window.location.href = "/login"; return; }
    setBusy(true); setMsg("");
    try {
      const ids = Object.keys(alloc);
      for (const pid of ids) {
        const body: any = { project_id: pid, votes: alloc[pid] };
        if (mode === "email") body.email = email;
        if (mode === "open") body.voter_id = voterId();
        await api(`/public/events/${params.slug}/ballot`, { method: "POST", body: JSON.stringify(body) });
      }
      setMsg("Votes cast — the tally stays hidden until voting closes.");
      await load(mode === "email" ? email : undefined);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <Link href={`/events/${params.slug}`}><I.back /> Back to event</Link>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Community vote</span>
        <h1>{box.event?.name}</h1>
        {!staff && box.open && (
          <p className="lead">You have <b className="countdown">{VOTES} votes</b> — spread them across any projects you like. Piling votes onto one project counts for less than broad support.</p>)}
      </div>

      {staff && (
        <div className="card">
          <h2>Ballot box — organizer view</h2>
          <p style={{ color: "var(--muted)" }}>
            {box.open ? "Voting is open." : "Voting is closed."} Mode: <b>{mode}</b>
            {turnout != null && <> · {turnout.voters} voter{turnout.voters === 1 ? "" : "s"} · {turnout.ballots} ballot{turnout.ballots === 1 ? "" : "s"}</>}
          </p>
          {standings.length > 0 ? (
            <><h3>Current standings{box.open ? " (live — public results publish at close)" : ""}</h3>
              {standings.map((r: any) => (
                <div key={r.project_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)" }}>
                  <span className="badge badge-track">#{r.rank}</span>
                  <b>{r.title}</b>
                  <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{r.votes} vote{r.votes === 1 ? "" : "s"} · score {Number(r.influence).toFixed(2)}</span>
                </div>))}</>
          ) : (
            <p style={{ color: "var(--muted)" }}>No votes cast yet — standings appear here once voting starts.</p>
          )}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
            <Link href="/organizer" className="btn-ghost btn-sm">Open voting settings</Link>
          </div>
          <p className="form-note" style={{ marginTop: 10 }}>Organizers don't cast votes here — use a participant account to vote.</p>
        </div>
      )}

      {!box.open && (
        <div className="card">
          <h2>{results ? "Final results" : "Voting is not open"}</h2>
          {!results && <p style={{ color: "var(--muted)" }}>{box.event?.voting_enabled ? "Voting has closed — results publish below once tallied." : "The organizer has not opened public voting for this event."}</p>}
          {results && (
            <>{(results.ranking || []).map((r: any) => (
              <div key={r.project_id} style={{ display: "flex", gap: 10, padding: "10px 0", borderTop: "1px solid var(--line)" }}>
                <span className="badge badge-track">#{r.rank}</span>
                <b>{r.title}</b>
                <span style={{ marginLeft: "auto", color: "var(--muted)" }}>{r.votes} vote{r.votes === 1 ? "" : "s"} · score {Number(r.influence).toFixed(2)}</span>
              </div>))}
              <p className="form-note">{results.turnout?.voters || 0} voters · {results.turnout?.ballots || 0} ballots</p></>
          )}
        </div>
      )}

      {box.open && !staff && (
        <div className="card field">
          <div className="deadline-bar"><I.spark /> Votes left: <b className="countdown">{left}</b>
            <span style={{ fontWeight: 400 }}>· {used} of {VOTES} placed</span></div>
          {savedTotal > 0 && (
            <p style={{ marginTop: 10 }}><span className="badge badge-ok"><span className="pip pip-green" /> Votes cast — {savedTotal} of {VOTES} placed</span>
              {dirty && <span style={{ color: "var(--muted)", fontSize: 13.5 }}> · unsaved changes below</span>}</p>
          )}
          {mode === "email" && (
            <div style={{ marginTop: 12 }}><label>Your email (one ballot set per address)</label>
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.org" inputMode="email" /></div>
          )}
          {mode === "auth" && !loggedIn && (
            <p><Link href="/login" className="btn btn-sm">Log in to vote</Link></p>
          )}
          {(box.projects || []).map((p: any) => (
            <div key={p.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
              <div style={{ flex: "2 1 220px" }}><b>{p.title}</b>
                <div style={{ fontSize: 13, color: "var(--muted)" }}>{p.summary}</div>
                {(saved[p.id] || 0) > 0 && <div style={{ fontSize: 12.5, color: "var(--leaf-deep)" }}>✓ {saved[p.id]} vote{saved[p.id] === 1 ? "" : "s"} cast</div>}</div>
              <span style={{ display: "flex", gap: 6, alignItems: "center", marginLeft: "auto" }}>
                <button type="button" className="btn-ghost btn-sm" disabled={busy || (alloc[p.id] || 0) <= 0} onClick={() => bump(p.id, -1)} aria-label={`Fewer votes for ${p.title}`}>−</button>
                <b className="countdown" style={{ minWidth: 44, textAlign: "center" }}>{alloc[p.id] || 0}</b>
                <button type="button" className="btn-ghost btn-sm" disabled={busy || (alloc[p.id] || 0) >= 10 || left <= 0} onClick={() => bump(p.id, 1)} aria-label={`More votes for ${p.title}`}>+</button>
              </span>
            </div>
          ))}
          {!box.projects?.length && <div className="card empty"><h3>No votable projects yet</h3><p>Projects appear here once submitted.</p></div>}
          {msg && <p>{msg}</p>}
          {!!box.projects?.length && <button className="btn" onClick={cast} disabled={busy}>Cast my votes <I.arrow /></button>}
        </div>
      )}
    </div>
  );
}
