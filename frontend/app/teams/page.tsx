"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";
import JudgeGate from "@/components/JudgeGate";

export default function Teams() {
  const [teams, setTeams] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [role, setRole] = useState("");
  const [msg, setMsg] = useState("");
  const [teamName, setTeamName] = useState("");
  const [eventId, setEventId] = useState("");
  const [joined, setJoined] = useState<boolean | null>(null);
  const [inviteInput, setInviteInput] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setRole(m.role);
      try {
        const [t, e] = await Promise.all([api("/teams"), api("/public/events").catch(() => ({ events: [] }))]);
        setTeams(t.teams || []);
        setEvents(e.events || []);
        // After event registration the event page redirects here with
        // ?event=<id> so the create form opens on the event just joined.
        const want = new URLSearchParams(window.location.search).get("event");
        if (want && (e.events || []).some((x: any) => x.id === want)) setEventId(want);
        else if (e.events?.[0]) setEventId(e.events[0].id);
      } catch (e: any) { setMsg(e.message); }
      finally { setLoading(false); }
    })();
  }, [router]);

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

  async function joinWithLink(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    const raw = inviteInput.trim();
    if (!raw) { setMsg("Paste an invite link or token first."); return; }
    const token = raw.includes("/teams/join/")
      ? raw.split("/teams/join/").pop()!.split(/[?#\s]/)[0]
      : raw.split(/\s/).pop()!;
    try {
      const d = await api(`/teams/join/${token}`, { method: "POST", body: "{}" });
      setInviteInput("");
      setMsg(d.already ? "You're already a member of this team." : "You've joined the team.");
      setTeams((await api("/teams")).teams || []);
    } catch (e: any) { setMsg(e.message); }
  }

  if (loading) return <div className="card"><div className="skel" style={{ height: 120 }} /></div>;
  if (role === "JUDGE") return <JudgeGate />;
  if ((role === "ORGANIZER" || role === "ADMIN") && !teams.length)
    return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
      <h1>Teams are a participant flow</h1>
      <p>Your organizer workspace lives under Overview — teams belong to participants competing in events.</p>
      <Link href="/dashboard" className="btn">Back to overview</Link></div>;

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Teams</span><h1>My teams</h1>
        <p className="lead">One team per event. Teammates join with your invite link — the roster locks once the team submits.</p></div>
      {msg && <div className="card"><p>{msg}</p></div>}
      <div className="card field">
        {!teams.length && <p style={{ color: "var(--muted)" }}>No team yet — create one below to unlock projects.</p>}
        {teams.map((t) => (
          <div key={t.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--line)" }}>
            <b><Link href={`/teams/${t.id}`}>{t.name}</Link></b>
            <span style={{ color: "var(--muted)" }}>— {(events.find((e) => e.id === t.event_id)?.name) || "Event"}</span>
            <button className="btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => invite(t.id)}>Copy invite link</button>
          </div>
        ))}
        <h3 style={{ marginTop: 16 }}>Join a team</h3>
        <p className="form-note">Got an invite link from a teammate? Paste it here.</p>
        <form onSubmit={joinWithLink} style={{ display: "flex", gap: 8 }}>
          <input value={inviteInput} onChange={(e) => setInviteInput(e.target.value)} placeholder="https://…/teams/join/…" style={{ flex: 1 }} />
          <button className="btn-ghost" type="submit">Join team</button>
        </form>
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
    </div>
  );
}
