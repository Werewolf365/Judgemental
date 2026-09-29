"use client";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";
export default function JoinTeam({ params }: { params: { token: string } }) {
  const [msg, setMsg] = useState("Verifying your invite…");
  const [ok, setOk] = useState(false);
  useEffect(() => {
    (async () => {
      if (!await fetchMe()) { window.location.href = "/login"; return; }
      try { const d = await api(`/teams/join/${params.token}`, { method: "POST", body: "{}" }); setOk(true); setMsg(d.already ? "You're already a member of this team." : "You've joined the team."); }
      catch (e: any) { setMsg("This invite didn't work: " + e.message); }
    })();
  }, [params.token]);
  return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
    <h1>{ok ? "Team joined" : "Join team"}</h1><p>{msg}</p>
    <a href="/teams" className="btn">View my teams <I.arrow /></a></div>;
}
