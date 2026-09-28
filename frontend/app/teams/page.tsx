"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe } from "@/lib/api";
import JudgeGate from "@/components/JudgeGate";

export default function Teams() {
  const [teams, setTeams] = useState<any[]>([]);
  const [role, setRole] = useState("");
  const [eventNames, setEventNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setRole(m.role);
      try {
        setTeams((await api("/teams")).teams || []);
        const ev = await api("/public/events").catch(() => ({ events: [] }));
        const map: Record<string, string> = {};
        for (const e of ev.events || []) map[e.id] = e.name;
        setEventNames(map);
      } finally { setLoading(false); }
    })();
  }, [router]);
  if (loading) return <div className="card"><div className="skel" style={{ height: 120 }} /></div>;
  if (role === "JUDGE") return <JudgeGate />;
  if ((role === "ORGANIZER" || role === "ADMIN") && !teams.length)
    return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
      <h1>Teams are a participant flow</h1>
      <p>Your organizer workspace lives under Overview — teams belong to participants competing in events.</p>
      <Link href="/dashboard" className="btn">Back to overview</Link></div>;
  return (
    <div>
      <div className="page-head"><span className="eyebrow">Teams</span><h1>My teams</h1></div>
      {!teams.length ? <div className="card empty"><h3>No teams yet</h3><p>Create one from your dashboard.</p><Link href="/dashboard" className="btn">Go to dashboard</Link></div> :
        teams.map((t) => <div key={t.id} className="card"><h2><Link href={`/teams/${t.id}`}>{t.name}</Link> <span style={{ color: "var(--muted)", fontWeight: 500, fontSize: 16 }}>— {eventNames[t.event_id] || "Event"}</span></h2><span className="mono">{t.id}</span></div>)}
    </div>
  );
}
