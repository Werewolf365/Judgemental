"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fetchMe, fmtDate } from "@/lib/api";
import { I } from "@/components/art";
import { Pager, paginate } from "@/components/Pager";

type CardState = { joined: boolean; teamId: string | null };

export default function Events() {
  const [events, setEvents] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [loggedIn, setLoggedIn] = useState(false);
  const [isStaff, setIsStaff] = useState(false);
  const [stateByEvent, setStateByEvent] = useState<Record<string, CardState>>({});
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      setLoggedIn(!!m);
      // Staff and judges run events; they are refused registration server-side,
      // so their cards must not offer a "Register" button at all.
      setIsStaff(!!m && ["ORGANIZER", "ADMIN", "JUDGE"].includes(m.role));
      const d = await api("/public/events").catch(() => ({ events: [] }));
      const list = d.events || [];
      setEvents(list);
      setLoaded(true);
      if (!m) return;
      // Membership + team per event, so cards reflect registration state.
      const teams: any[] = await api("/teams").then((t) => t.teams || []).catch(() => []);
      const teamByEvent: Record<string, string> = {};
      for (const t of teams) teamByEvent[t.event_id] = t.id;
      const entries = await Promise.all(
        list.map(async (e: any) => {
          const mm = await api(`/events/${e.id}/membership`).catch(() => ({ joined: false }));
          return [e.id, { joined: !!mm.joined, teamId: teamByEvent[e.id] || mm.team_id || null }] as const;
        })
      );
      setStateByEvent(Object.fromEntries(entries));
    })().catch((e) => { setNotice(e.message); setLoaded(true); });
  }, []);
  const shown = events.filter((e) => !q.trim() || e.name.toLowerCase().includes(q.trim().toLowerCase()));

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Events</span>
        <h1>Find your hackathon</h1><p className="lead">Published events with live deadlines. Pick one, join, and start building.</p></div>
      <div className="card" style={{ display: "flex", gap: 10 }}>
        <input aria-label="Search events" placeholder="Search events…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }}
          style={{ flex: 1, padding: "11px 13px", borderRadius: 10, border: "1px solid #c9d8e8", font: "inherit" }} />
      </div>
      {!loaded && <div className="card"><div className="skel" style={{ height: 90 }} /></div>}
      {notice && <div className="form-error">{notice}</div>}
      {loaded && !shown.length && <div className="card empty"><h3>{events.length ? "No events match" : "No published events yet"}</h3><p>{events.length ? "Try a different search." : "An organizer needs to publish one first."}</p></div>}
      <div className="grid grid-2">
        {paginate(shown, page).map((e) => {
          const st = stateByEvent[e.id];
          // Registration window is server-enforced; mirror it so the card
          // never offers a form that is guaranteed to bounce.
          const t = Date.now();
          const rc = e.registration_close ? new Date(e.registration_close).getTime() : null;
          const ro = e.registration_start ? new Date(e.registration_start).getTime() : null;
          const closed = rc != null && t > rc;
          const notOpen = ro != null && t < ro;
          return (
            <div key={e.id} className="card">
              <span className="badge badge-ok"><span className="pip pip-green" /> Open for builders</span>
              <h2 style={{ marginTop: 8 }}><Link href={`/events/${e.slug}`}>{e.name}</Link></h2>
              <p style={{ color: "var(--muted)" }}><I.clock /> Submissions close <b className="countdown">{fmtDate(e.submissions_close)}</b></p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                {!loggedIn && <Link href="/login" className="btn btn-sm">Log in to join</Link>}
                {loggedIn && isStaff && <span className="badge badge-track" title="Staff and judges run events rather than competing in them."><I.team /> Staff account</span>}
                {loggedIn && !isStaff && !st?.joined && !closed && !notOpen && <Link href={`/events/${e.slug}`} className="btn btn-sm">Register <I.arrow /></Link>}
                {loggedIn && !isStaff && !st?.joined && closed && <span className="badge badge-muted"><I.clock /> Registration closed</span>}
                {loggedIn && !isStaff && !st?.joined && notOpen && <span className="badge badge-muted"><I.clock /> Opens {fmtDate(e.registration_start)}</span>}
                {loggedIn && !isStaff && st?.joined && <span className="badge badge-ok"><span className="pip pip-green" /> Registered</span>}
                {loggedIn && st?.joined && st?.teamId && !isStaff && (
                  <Link href={`/submissions/new?team=${st.teamId}`} className="btn btn-sm">Submit project <I.arrow /></Link>
                )}
                <Link href={`/events/${e.slug}`} className="btn-ghost btn-sm">View details</Link>
              </div>
            </div>
          );
        })}
      </div>
      {loaded && !!shown.length && <div className="card"><Pager page={page} total={shown.length} onPage={setPage} /></div>}
    </div>
  );
}
