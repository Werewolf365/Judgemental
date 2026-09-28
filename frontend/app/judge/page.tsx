"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";

const STATUS_TONE: Record<string, string> = {
  ASSIGNED: "badge-warn",
  IN_PROGRESS: "badge-track",
  COMPLETED: "badge-ok",
  REVOKED: "badge-muted",
};

export default function JudgeHome() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState("");
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      if (m.role !== "JUDGE") { setMsg("Judging is for accounts with the JUDGE role."); setLoading(false); return; }
      try { setItems((await api("/judge/assignments")).assignments || []); }
      catch (e: any) { setMsg(e.message); }
      finally { setLoading(false); }
    })();
  }, [router]);

  if (loading) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;
  if (msg) return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
    <h1>Judging</h1><p>{msg}</p><Link href="/dashboard" className="btn">Back to workspace</Link></div>;

  const open = items.filter((a) => a.status === "ASSIGNED" || a.status === "IN_PROGRESS");
  const done = items.filter((a) => a.status === "COMPLETED");

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Judging</span>
        <h1>My assignments</h1>
        <p className="lead">{open.length} awaiting your scores · {done.length} submitted. You only ever see projects assigned to you.</p></div>
      {!items.length && <div className="card empty"><h3>No assignments yet</h3>
        <p>An organizer adds you to an event first — assigned projects will appear here.</p></div>}
      {items.map((a) => (
        <div key={a.id} className="card" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ flex: "2 1 240px" }}>
            <b><Link href={`/judge/score/${a.id}`}>{a.project_title}</Link></b>
            <div style={{ color: "var(--muted)", fontSize: 14 }}>{a.track}</div>
          </div>
          <span className={`badge ${STATUS_TONE[a.status] || "badge-muted"}`}>{a.status.replace("_", " ")}</span>
          {(a.status === "ASSIGNED" || a.status === "IN_PROGRESS") && (
            <Link href={`/judge/score/${a.id}`} className="btn btn-sm" style={{ marginLeft: "auto" }}>
              {a.status === "ASSIGNED" ? "Start scoring" : "Continue"} <I.arrow /></Link>
          )}
        </div>
      ))}
    </div>
  );
}
