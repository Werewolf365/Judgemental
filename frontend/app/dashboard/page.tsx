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
  const [teamName, setTeamName] = useState("");
  const [eventId, setEventId] = useState("");
  const [joined, setJoined] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [t, s, e] = await Promise.all([api("/teams"), api("/submissions"), api("/public/events")]);
        setTeams(t.teams || []); setSubs(s.projects || []); setEvents(e.events || []);
        if (e.events?.[0]) setEventId(e.events[0].id);
      } catch (e: any) { setMsg(e.message); }
      finally { setLoading(false); }
    })();
  }, []);

  const stage: number = !teams.length ? 1 : !subs.length ? 3 : 4;
  const nextAction = !teams.length ? "Create your team below" : subs.some((s) => s.status === "DRAFT") ? "Finish and submit your draft" : subs.length ? "You're submitted" : "Start your project";

  useEffect(() => {
    if (!eventId) return;
    api(`/events/${eventId}/membership`).then((m) => setJoined(m.joined)).catch(() => setJoined(null));
  }, [eventId, teams]);

  async function createTeam(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!eventId || !teamName.trim()) { setMsg("Pick an event and a team name."); return; }
    try {
      const m = await api(`/events/${eventId}/membership`).catch(() => null);
      if (m && !m.joined) {
        setMsg("You must register for this event first. Click 'Register for this event first' below.");
        return;
      }
      await api(`/events/${eventId}/teams`, { method: "POST", body: JSON.stringify({ name: teamName.trim() }) });
      setTeamName(""); setJoined(true); setMsg("Team created — now copy an invite link for your teammates.");
      setTeams((await api("/teams")).teams || []);
    } catch (e: any) { setMsg(e.message); }
  }

  function joinSelected() {
    if (!eventId) return;
    const ev = events.find((e) => e.id === eventId);
    if (ev) window.location.href = `/events/${ev.slug || ev.id}`;
  }

  async function invite(teamId: string) {
    setMsg("");
    try {
      const d = await api(`/teams/${teamId}/invites`, { method: "POST", body: "{}" });
      const url = `${window.location.origin}/teams/join/${d.token}`;
      await navigator.clipboard.writeText(url).catch(() => {});
      setMsg(`Invite link copied to clipboard: ${url}`);
    } catch (e: any) { setMsg(e.message); }
  }

  if (loading) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;

  const step = (n: number, title: string, sub: string) => (
    <div key={n} className={`step ${stage > n ? "done" : stage === n ? "now" : ""}`}>
      <b><span className="n">{stage > n ? "✓" : n}</span> {title}</b>{sub}
    </div>
  );

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Workspace</span>
        <h1>Workspace{me?.display_name ? ` — ${me.display_name}` : ""}</h1><p className="lead">Next up: <b>{nextAction}</b></p></div>

      <div className="card">
        <div className="steps" aria-label="Progress">
          {step(1, "Join event", joined ? "Registered" : events.length ? "Pick an event below" : "Browse events")}
          {step(2, "Create team", teams.length ? teams[0].name : "Pending")}
          {step(3, "Invite members", stage > 3 ? "Link ready" : "Pending")}
          {step(4, "Submit", subs.some((s) => s.status === "SUBMITTED") ? "Submitted" : "Pending")}
        </div>
        {msg && <p>{msg}</p>}
      </div>

      <div className="grid grid-2">
        <div className="card field">
          <h2><I.team /> My teams</h2>
          {!teams.length && <p style={{ color: "var(--muted)" }}>No team yet — create one to unlock projects.</p>}
          {teams.map((t) => (
            <div key={t.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--line)" }}>
              <b><Link href={`/teams/${t.id}`}>{t.name}</Link></b>
              <span style={{ color: "var(--muted)" }}>— {(events.find((e) => e.id === t.event_id)?.name) || "Event"}</span>
              <button className="btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => invite(t.id)}>Copy invite link</button>
            </div>
          ))}
          <h3 style={{ marginTop: 16 }}>Create a team</h3>
          <form onSubmit={createTeam}>
            <label>Event</label>
            <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
              {events.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            {joined === false && (
              <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", margin: "4px 0 8px" }}>
                <button type="button" className="btn-ghost btn-sm" onClick={joinSelected}>Register for this event first</button>
              </div>
            )}
            {joined === true && <p className="form-note">You're registered for this event.</p>}
            <label>Team name</label>
            <input value={teamName} onChange={(e) => setTeamName(e.target.value)} placeholder="Nightshift" />
            <button className="btn" type="submit">Create team <I.arrow /></button>
          </form>
        </div>
        <div className="card">
          <h2><I.doc /> My submissions</h2>
          {!teams.length ? (
            <div className="empty"><h3>Submissions unlock with a team</h3>
              <p>Register for an event and create or join a team first — your drafts and submissions will live here.</p></div>
          ) : (
            <>
              {!subs.length && <div className="empty"><h3>No projects yet</h3><p>Create your first draft to get started.</p></div>}
              {subs.map((s) => (
                <div key={s.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
                  <b><Link href={`/submissions/${s.id}/edit`}>{s.title}</Link></b>{" "}
                  <span className={`badge ${s.status === "SUBMITTED" ? "badge-ok" : "badge-warn"}`}><span className={`pip ${s.status === "SUBMITTED" ? "pip-green" : "pip-amber"}`} />{s.status}</span>
                </div>
              ))}
              <div style={{ marginTop: 12 }}><Link href="/submissions/new" className="btn">New project <I.arrow /></Link></div>
            </>
          )}
        </div>
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
