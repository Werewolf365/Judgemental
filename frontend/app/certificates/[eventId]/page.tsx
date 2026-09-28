"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Participant certificate: organizer base image with the recipient's
 *  details overlaid, printable to PDF via the browser. Issued lazily by
 *  the API on first view (only after results are declared). */
export default function CertificateView({ params }: { params: { eventId: string } }) {
  const [cert, setCert] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api(`/events/${params.eventId}/certificate`)
      .then(setCert)
      .catch((e: any) => setErr(e.message));
  }, [params.eventId]);
  if (err) return <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
    <h3>No certificate yet</h3><p>{err}</p>
    <Link href="/dashboard" className="btn">Back to workspace</Link></div>;
  if (!cert) return <div className="card"><div className="skel" style={{ height: 300 }} /></div>;
  const winner = cert.kind === "WINNER";
  const when = cert.issued_at ? new Date(cert.issued_at).toLocaleDateString() : "";
  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div className="page-head"><span className="eyebrow">Certificate</span>
        <h1>{cert.event_name}</h1></div>
      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div style={{
          position: "relative", width: "100%", aspectRatio: "4 / 3",
          background: cert.template_image
            ? `url(${cert.template_image}) center / cover no-repeat`
            : "linear-gradient(160deg, #0a4a56 0%, #0b7d8f 52%, #34b37a 100%)",
          display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
        }}>
          <div style={{
            padding: "28px 40px", maxWidth: "80%",
            background: cert.template_image ? "rgba(255,255,255,.82)" : "transparent",
            borderRadius: 12,
            color: cert.template_image ? "var(--sea-950)" : "#fff",
          }}>
            <div style={{ fontSize: 13, letterSpacing: 3, fontWeight: 700, opacity: .8 }}>
              {winner ? "WINNER" : "CERTIFICATE OF PARTICIPATION"}</div>
            <div style={{ fontSize: 34, fontWeight: 800, margin: "8px 0" }}>{cert.display_name}</div>
            <div style={{ fontSize: 14.5 }}>
              {winner ? <>for winning <b>{cert.event_name}</b>{cert.team_name ? <> with team <b>{cert.team_name}</b></> : null}</>
                : <>for participating in <b>{cert.event_name}</b>{cert.team_name ? <> with team <b>{cert.team_name}</b></> : null}</>}
            </div>
            <div style={{ fontSize: 12.5, marginTop: 10, opacity: .75 }}>
              {when}{cert.code ? ` · Verify: ${cert.code}` : ""}</div>
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 10, marginTop: 12, flexWrap: "wrap" }}>
        <button className="btn" onClick={() => window.print()}>Print / Save as PDF</button>
        <Link href="/dashboard" className="btn-ghost">Back to workspace</Link>
      </div>
      <p className="form-note">Tip: choose Landscape in the print dialog for a full-page certificate.</p>
    </div>
  );
}
