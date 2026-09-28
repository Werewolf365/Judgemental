"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fmtDate } from "@/lib/api";
import { ProjectArt, I } from "@/components/art";
import Comments from "@/components/Comments";

export default function Detail({ params }: { params: { slug: string, projectId: string } }) {
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api(`/public/projects/${params.projectId}`).then((d) => setP(d.project)).catch((e) => setErr(e.message)); }, [params.projectId]);
  if (err) return <div className="card empty"><h3>Project not found</h3><p>{err}</p><Link href={`/events/${params.slug}/projects`}><I.back /> Back to gallery</Link></div>;
  if (!p) return <div className="card"><div className="skel" style={{ height: 220 }} /></div>;
  return (
    <div>
      <Link href={`/events/${params.slug}/projects`}><I.back /> Back to gallery</Link>
      <div className="card" style={{ padding: 0 }}>
        <ProjectArt id={p.id} h={190} />
        <div style={{ padding: 26 }}>
          <span className="badge badge-track">{p.track}</span>{" "}
          <span className="badge badge-muted">by {p.team}</span>
          <h1 style={{ marginTop: 10 }}>{p.title}</h1>
          <p className="lead">{p.summary}</p>
          {p.members?.length > 0 && <p style={{ color: "var(--muted)" }}><I.team /> {p.members.join(" · ")}</p>}
          {(p.custom_fields || []).map((c: any, i: number) => (
            <p key={i}><b>{c.label}</b><br />{c.value}</p>
          ))}
          {p.description && <p>{p.description}</p>}
          <div style={{ display: "flex", gap: 10, marginTop: 14, flexWrap: "wrap" }}>
            {p.repo_url && <a className="btn-ghost btn-sm" href={p.repo_url} target="_blank" rel="noreferrer"><I.code /> Repository</a>}
            {p.demo_url && <a className="btn-ghost btn-sm" href={p.demo_url} target="_blank" rel="noreferrer"><I.play /> Live demo</a>}
          </div>
          <p style={{ color: "var(--muted)", marginTop: 14, fontSize: 13.5 }}>Submitted {fmtDate(p.submitted_at)}</p>
        </div>
      </div>
      <Comments projectId={p.id} />
    </div>
  );
}
