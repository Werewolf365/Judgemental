"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";
import JudgeGate from "@/components/JudgeGate";

export default function Submissions() {
  const [subs, setSubs] = useState<any[]>([]);
  const [teamed, setTeamed] = useState<boolean | null>(null);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setRole(m.role);
      try {
        setSubs((await api("/submissions")).projects || []);
        setTeamed(((await api("/teams")).teams || []).length > 0);
      } finally { setLoading(false); }
    })();
  }, [router]);
  if (loading) return <div className="card"><div className="skel" style={{ height: 120 }} /></div>;
  if (role === "JUDGE") return <JudgeGate />;
  if (teamed === false) return (
    <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
      <h1>Submissions unlock with a team</h1>
      <p>Register for an event and create or join a team first — your drafts and submissions will live here.</p>
      <Link href="/dashboard" className="btn">Go to workspace <I.arrow /></Link>
    </div>
  );
  return (
    <div>
      <div className="page-head" style={{ display: "flex", alignItems: "center" }}>
        <div><span className="eyebrow"><span className="dot" /> Submissions</span><h1>My projects</h1></div>
        <Link href="/submissions/new" className="btn" style={{ marginLeft: "auto" }}>New project <I.arrow /></Link>
      </div>
      {!subs.length && <div className="card empty"><h3>Nothing here yet</h3><p>Drafts you save will appear here.</p></div>}
      {subs.map((s) => (
        <div key={s.id} className="card" style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <div><b><Link href={`/submissions/${s.id}/edit`}>{s.title}</Link></b>
            <div style={{ color: "var(--muted)", fontSize: 14 }}>{s.summary}</div></div>
          <span className={`badge ${s.status === "SUBMITTED" ? "badge-ok" : "badge-warn"}`} style={{ marginLeft: "auto" }}><span className={`pip ${s.status === "SUBMITTED" ? "pip-green" : "pip-amber"}`} />{s.status}</span>
        </div>
      ))}
    </div>
  );
}
