"use client";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";

export default function TeamDetail({ params }: { params: { id: string } }) {
  const [team, setTeam] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [msg, setMsg] = useState("");
  useEffect(() => {
    (async () => {
      const m = await fetchMe(); setMe(m);
      if (!m) { window.location.href = "/login"; return; }
      try { setTeam((await api(`/teams/${params.id}`)).team); }
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
  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Team</span><h1>{team.name}</h1></div>
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
