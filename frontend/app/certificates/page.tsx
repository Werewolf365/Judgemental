"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Pager, paginate } from "@/components/Pager";

/** Participant certificate shelf: every joined event with its certificate
 *  state. Reached from the nav bar ("My certificates"). */
export default function Certificates() {
  const [certs, setCerts] = useState<any[] | null>(null);
  const [page, setPage] = useState(1);
  useEffect(() => {
    api("/certificates/mine").then((d) => setCerts(d.certificates || [])).catch(() => setCerts([]));
  }, []);
  if (certs === null) return <div className="card"><div className="skel" style={{ height: 120 }} /></div>;
  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <div className="page-head"><span className="eyebrow">Certificates</span><h1>My certificates</h1>
        <p className="lead">Issued automatically once an event's results are declared — winner for the rank-1 team, participation for everyone else.</p></div>
      <div className="card field">
        {!certs.length && <p style={{ color: "var(--muted)" }}>No event registrations yet — certificates unlock here once results are declared.</p>}
        {certs && paginate(certs, page).map((c: any) => (
          <div key={c.event_id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
            <div><b style={{ fontSize: 16 }}>{c.event_name}</b>
              <div style={{ fontSize: 13, color: "var(--muted)" }}>
                {c.declared ? (c.kind === "WINNER" ? "Winner" : "Participation") : "Results not declared yet"}</div></div>
            {c.declared
              ? <Link href={`/certificates/${c.event_id}`} className="btn-ghost btn-sm" style={{ marginLeft: "auto" }}>View certificate</Link>
              : <span className="badge badge-muted" style={{ marginLeft: "auto" }}>Pending</span>}
          </div>
        ))}
        {certs && <Pager page={page} total={certs.length} onPage={setPage} />}
      </div>
    </div>
  );
}
