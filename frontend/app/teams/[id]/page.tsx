"use client";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";

export default function TeamDetail({ params }: { params: { id: string } }) {
  const [team, setTeam] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [proj, setProj] = useState<any>(null);
  const [projChecked, setProjChecked] = useState(false);
  const [trackName, setTrackName] = useState("");
  useEffect(() => {
    (async () => {
      const m = await fetchMe(); setMe(m);
      if (!m) { window.location.href = "/login"; return; }
      try {
        const t = (await api(`/teams/${params.id}`)).team;
        setTeam(t);
        // One submission per team, one track per submission: the project is
        // the single source of truth for "which track is this team on".
        try {
          const s = await api("/submissions").catch(() => ({ projects: [] }));
          const mine = (s.projects || []).find((p: any) => p.team_id === params.id) || null;
          setProj(mine);
          if (mine?.track_id) {
            const tr = await api(`/events/${t.event_id}/tracks`).catch(() => ({ tracks: [] }));
            const hit = (tr.tracks || []).find((x: any) => x.id === mine.track_id);
            setTrackName(hit ? hit.name : "");
          }
        } catch { /* staff/edge: project card simply stays hidden */ }
        finally { setProjChecked(true); }
      }
      catch (e: any) { setMsg(e.message); }
    })();
  }, [params.id]);

  async function invite() {
    try {
      const d = await api(`/teams/${params.id}/invites`, { method: "POST", body: "{}" });
      const url = `${window.location.origin}/teams/join/${d.token}`;
      await navigator.clipboard.writeText(url).catch(() => {});
      setMsg(`Invite link copied to clipboard: ${url}`);
    } catch (e: any) { setMsg(e.message); }
  }

  async function leave() {
    if (!confirm("Leave this team? If you're the last member the team is dissolved. You can't leave after the team has submitted.")) return;
    try {
      const d = await api(`/teams/${params.id}/members/me`, { method: "DELETE" });
      setMsg(d.dissolved ? "Team dissolved." : "You've left the team.");
      setTimeout(() => { window.location.href = "/dashboard"; }, 800);
    } catch (e: any) { setMsg(e.message); }
  }

  if (!team) return <div className="card">{msg || "Loading…"}</div>;
  const isCaptain = team.members?.some((m: any) => m.user_id === me?.id && m.role === "CAPTAIN");
  const isMember = team.members?.some((m: any) => m.user_id === me?.id);
  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Team</span><h1>{team.name}</h1></div>
      {isMember && projChecked && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2><I.doc /> Team project</h2>
          {proj ? (
            <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
              <b><a href={`/submissions/${proj.id}/edit`}>{proj.title}</a></b>
              {trackName && <span className="badge badge-track">{trackName}</span>}
              <span className={`badge ${proj.status === "SUBMITTED" ? "badge-ok" : "badge-warn"}`}>{proj.status}</span>
            </div>
          ) : (
            <p style={{ color: "var(--muted)", margin: 0 }}>No project yet — the team picks one track when it creates its project, so nobody can end up on a different track.</p>
          )}
        </div>
      )}
      <div className="grid grid-2">
        <div className="card"><h2><I.team /> Members ({team.members?.length || 0})</h2>
          {(team.members || []).map((m: any) => (
            <div key={m.user_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)" }}>
              <b>{m.display_name}</b><span style={{ color: "var(--muted)" }}>{m.email}</span>
              {m.role === "CAPTAIN" && <span className="badge badge-navy" style={{ marginLeft: "auto" }}>Captain</span>}
            </div>
          ))}
        </div>
        <div className="card"><h2>Invite link</h2>
          {isCaptain ? (<><p style={{ color: "var(--muted)" }}>Share this with teammates. Regenerating revokes the previous link.</p>
            <button className="btn" onClick={invite}>Generate and copy invite <I.arrow /></button></>)
            : <p style={{ color: "var(--muted)" }}>Only the captain can generate invites.</p>}
          {msg && <p>{msg}</p>}
          <button className="link-btn" onClick={leave}>Leave team</button>
        </div>
      </div>
    </div>
  );
}
