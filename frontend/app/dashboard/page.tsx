"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe, fmtDate, type Me } from "@/lib/api";
import { I } from "@/components/art";
import Popup from "@/components/Popup";

type OrgEvent = { event: any; stats: any };

function OrganizerHome({ me }: { me: Me }) {
  const [items, setItems] = useState<OrgEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const [notice, setNotice] = useState<{ title: string; body: React.ReactNode } | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const list = await api("/events");
        const rows: OrgEvent[] = [];
        for (const e of list.events || []) {
          try { rows.push(await api(`/events/${e.id}/stats`)); }
          catch { rows.push({ event: e, stats: null }); }
        }
        setItems(rows);
      } catch (e: any) { setMsg(e.message); }
      finally { setLoading(false); }
    })();
  }, []);

  async function togglePublish(ev: any) {
    setMsg("");
    try {
      const pub = ev.status !== "PUBLISHED";
      const d = await api(`/events/${ev.id}/${pub ? "publish" : "unpublish"}`, { method: "POST", body: "{}" });
      const rows: OrgEvent[] = [];
      const list = await api("/events");
      for (const e of list.events || []) {
        try { rows.push(await api(`/events/${e.id}/stats`)); }
        catch { rows.push({ event: e, stats: null }); }
      }
      setItems(rows);
      // Publishing is the outcome the whole wizard is driving at, so it gets
      // a popup rather than a line of text in a scrolled-past panel.
      setNotice(pub
        ? { title: "Event published", body: <>“{d.event.name}” is live. It now shows in the <b>Events</b> list and anyone can open it to register.</> }
        : { title: "Moved back to draft", body: <>“{d.event.name}” is hidden from the Events list and the gallery again.</> });
    } catch (e: any) { setMsg(e.message); }
  }

  if (loading) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;
  return (
    <div>
      {notice && (
        <Popup kind={notice.title.startsWith("Moved") ? "info" : "ok"} title={notice.title}
          dismissLabel="Got it" onClose={() => setNotice(null)}>
          {notice.body}
        </Popup>
      )}
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Mission control</span>
        <h1>Event overview</h1>
        <p className="lead">Every event you run — status, dates, tracks, prizes, and submission activity at a glance.</p></div>
      {msg && <div className="card"><p>{msg}</p></div>}
      {!items.length && <div className="card empty"><h3>No events yet</h3><p>Create your first event to get started.</p><Link href="/organizer" className="btn">Open event console <I.arrow /></Link></div>}
      <div className="grid grid-2">
        {items.map(({ event: e, stats: s }) => (
          <div key={e.id} className="card">
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <span className={`badge ${e.status === "PUBLISHED" ? "badge-ok" : "badge-muted"}`}>
                <span className={`pip ${e.status === "PUBLISHED" ? "pip-green" : "pip-grey"}`} />{e.status}
              </span>
              <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}><I.clock /> closes {fmtDate(e.submissions_close)}</span>
            </div>
            <h2 style={{ marginTop: 8 }}>{e.name}</h2>
            <p style={{ fontSize: 13, color: "var(--muted)" }}>Gallery: <b>{({ PUBLIC: "Public", PARTICIPANTS: "Participants", ORGANIZERS_ONLY: "Organizers only" } as any)[e.gallery_visibility] || "Public"}</b></p>
            {s ? (
              <div className="grid grid-3" style={{ marginTop: 6 }}>
                <div><b style={{ fontSize: 22 }}>{s.participants}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Joined</div></div>
                <div><b style={{ fontSize: 22 }}>{s.teams}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Teams</div></div>
                <div><b style={{ fontSize: 22 }}>{s.submitted}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Submitted</div></div>
                <div><b style={{ fontSize: 22 }}>{s.tracks}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Tracks</div></div>
                <div><b style={{ fontSize: 22 }}>{s.prizes}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Prizes</div></div>
                <div><b style={{ fontSize: 22 }}>{s.drafts}</b><div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: ".06em" }}>Drafts</div></div>
              </div>
            ) : <p style={{ color: "var(--muted)" }}>Stats unavailable.</p>}
            <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
              <Link href={`/organizer?event=${e.id}`} className="btn btn-sm">Manage <I.arrow /></Link>
              <Link href={`/events/${e.slug}/projects`} className="btn-ghost btn-sm">Gallery</Link>
              <button className="btn-ghost btn-sm" onClick={() => togglePublish(e)}>{e.status === "PUBLISHED" ? "Unpublish" : "Publish"}</button>
              {e.status === "PUBLISHED"
                ? <Link href={`/events/${e.slug}`} className="btn-ghost btn-sm">Public page</Link>
                : <Link href={`/events/${e.slug}`} className="btn-ghost btn-sm">Preview draft</Link>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ParticipantHome({ me }: { me: Me }) {
  const [teams, setTeams] = useState<any[]>([]);
  const [subs, setSubs] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [certs, setCerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [t, s, e] = await Promise.all([api("/teams"), api("/submissions"), api("/public/events")]);
        setTeams(t.teams || []); setSubs(s.projects || []); setEvents(e.events || []);
        setCerts(((await api("/certificates/mine").catch(() => ({ certificates: [] }))).certificates || []));
      } catch (e: any) { setMsg(e.message); }
      finally { setLoading(false); }
    })();
  }, []);

  const nextAction = !teams.length ? "Create or join a team under My teams" : subs.some((s) => s.status === "DRAFT") ? "Finish and submit your draft" : subs.length ? "You're submitted" : "Start your project";
  const past = (iso?: string | null) => !!iso && new Date(iso).getTime() <= Date.now();
  const subByTeam: Record<string, any> = {};
  for (const s of subs) if (!subByTeam[s.team_id]) subByTeam[s.team_id] = s;

  if (loading) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Workspace</span>
        <h1>Workspace{me?.display_name ? ` — ${me.display_name}` : ""}</h1><p className="lead">Next up: <b>{nextAction}</b></p></div>
      {msg && <div className="card"><p>{msg}</p></div>}

      <div className="card">
        <h2><I.doc /> My projects</h2>
        {!teams.length ? (
          <div className="empty"><h3>No team yet</h3>
            <p>Projects belong to teams — <Link href="/teams">create or join one under My teams</Link>, then come back here.</p>
            <div style={{ marginTop: 12 }}><Link href="/teams" className="btn">Go to My teams <I.arrow /></Link></div></div>
        ) : (
          <>
            {teams.map((t) => {
              const ev = events.find((e) => e.id === t.event_id);
              const sub = subByTeam[t.id];
              const shut = past(ev?.submissions_close);
              return (
                <div key={t.id} style={{ padding: "12px 0", borderTop: "1px solid var(--line)" }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
                    <b style={{ fontSize: 16 }}><Link href={`/teams/${t.id}`}>{t.name}</Link></b>
                    <span style={{ color: "var(--muted)", fontSize: 13.5 }}>{ev?.name || "Event"}</span>
                  </div>
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginTop: 6 }}>
                    {sub ? (
                      <><Link href={`/submissions/${sub.id}/edit`}><b>{sub.title}</b></Link>
                        <span className={`badge ${sub.status === "SUBMITTED" ? "badge-ok" : "badge-warn"}`}>
                          <span className={`pip ${sub.status === "SUBMITTED" ? "pip-green" : "pip-amber"}`} />{sub.status}</span></>
                    ) : (
                      <><span style={{ color: "var(--muted)" }}>No project yet</span>
                        {!shut && <Link href="/submissions/new" className="btn-ghost btn-sm">Start a draft <I.arrow /></Link>}</>
                    )}
                    <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}>
                      <I.clock /> {shut ? "Submissions closed" : <>deadline {fmtDate(ev?.submissions_close)}</>}
                    </span>
                  </div>
                </div>
              );
            })}
            {(() => {
              const needsOpen = teams.filter((t) => {
                if (subByTeam[t.id]) return false;
                const dl = events.find((e) => e.id === t.event_id)?.submissions_close;
                return !past(dl);
              });
              if (teams.every((t) => subByTeam[t.id]))
                return <p className="form-note" style={{ marginTop: 12 }}>Each of your teams already has its project — one submission per team.</p>;
              if (needsOpen.length)
                return <div style={{ marginTop: 12 }}><Link href="/submissions/new" className="btn">New project <I.arrow /></Link></div>;
              return <p className="form-note" style={{ marginTop: 12 }}>Submissions are closed for your events — nothing left to start.</p>;
            })()}
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>My certificates</h2>
        {!certs.length && <p style={{ color: "var(--muted)" }}>No event registrations yet — certificates unlock here once results are declared.</p>}
        {certs.map((c: any) => (
          <div key={c.event_id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
            <div><b>{c.event_name}</b>
              <div style={{ fontSize: 13, color: "var(--muted)" }}>
                {c.declared ? (c.kind === "WINNER" ? "Winner" : "Participation") : "Results not declared yet"}</div></div>
            {c.declared
              ? <Link href={`/certificates/${c.event_id}`} className="btn-ghost btn-sm" style={{ marginLeft: "auto" }}>View certificate</Link>
              : <span className="badge badge-muted" style={{ marginLeft: "auto" }}>Pending</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();
  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setMe(m); setReady(true);
    })();
  }, [router]);
  if (!ready) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;
  // Judges cannot use the participant workspace (team creation needs event
  // membership, which their role is refused server-side), so /dashboard
  // forwards them to their own console instead of a dead end.
  if (me?.role === "JUDGE") { router.push("/judge"); return <div className="card">Opening your judging console…</div>; }
  const isOrg = me?.role === "ORGANIZER" || me?.role === "ADMIN";
  return isOrg ? <OrganizerHome me={me} /> : <ParticipantHome me={me} />;
}
