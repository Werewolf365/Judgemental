"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { ProjectArt, I } from "@/components/art";

function Inner({ event }: { event: string }) {
  const sp = useSearchParams();
  const [q, setQ] = useState(sp.get("q") || "");
  const [track, setTrack] = useState(sp.get("track") || "");
  const [tracks, setTracks] = useState<any[]>([]);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [eventName, setEventName] = useState("");
  const [isDraft, setIsDraft] = useState(false);

  async function load(p = 1, qq = q, tt = track) {
    setLoading(true); setErr("");
    try {
      const d = await api(`/public/events/${event}/projects?q=${encodeURIComponent(qq)}&track=${encodeURIComponent(tt)}&page=${p}&page_size=12`);
      setItems(d.projects); setTotal(d.total); setPage(d.page);
      const url = new URL(window.location.href);
      url.searchParams.set("q", qq); url.searchParams.set("track", tt);
      url.searchParams.set("page", String(p));
      window.history.replaceState(null, "", url.toString());
    } catch (e: any) { setErr(e.message); setItems([]); setTotal(0); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    // Organizers/admins can preview draft galleries; everyone else only sees published ones.
    api(`/public/events/${event}`).then((d) => { setTracks(d.tracks || []); setEventName(d.event?.name || ""); }).catch(() => {
      api(`/events/${event}`).then((d) => { setEventName(d.event?.name || ""); setIsDraft(true); }).catch(() => {});
    });
    load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <Link href={`/events/${event}`}><I.back /> Back to event</Link>
      {isDraft && <div className="deadline-bar" style={{ marginTop: 12 }}>Draft preview — this gallery is visible to organizers only until the event is published.</div>}
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Showcase{eventName ? ` — ${eventName}` : ""}</span>
        <h1>Project gallery</h1><p className="lead">{total} submitted projects{eventName ? ` in ${eventName}` : ""}. Search and filter — results come straight from the server.</p></div>
      <div className="card" style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input aria-label="Search projects" placeholder="Search title, summary, team…" value={q}
          onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(1)}
          style={{ flex: "2 1 240px", padding: "11px 13px", borderRadius: 10, border: "1px solid #c9d8e8", font: "inherit" }} />
        <select aria-label="Filter by track" value={track} onChange={(e) => { setTrack(e.target.value); load(1, q, e.target.value); }}
          style={{ flex: "1 1 180px", padding: "11px 13px", borderRadius: 10, border: "1px solid #c9d8e8", font: "inherit" }}>
          <option value="">All tracks</option>
          {tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <button className="btn" onClick={() => load(1)}>Search</button>
      </div>
      {loading ? (
        <div className="grid grid-3">{[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="card"><div className="skel" style={{ height: 150 }} /></div>)}</div>
      ) : err ? (
        <div className="card empty"><h3>Gallery unavailable</h3><p>{err}</p><Link href="/events">Browse events</Link></div>
      ) : !items.length ? (
        <div className="card empty"><h3>No projects match</h3><p>Try a different search term or clear the track filter.</p>
          <button className="btn-ghost btn-sm" onClick={() => { setQ(""); setTrack(""); load(1, "", ""); }}>Clear filters</button></div>
      ) : (
        <div className="grid grid-3">
          {items.map((p) => (
            <Link key={p.id} href={`/events/${event}/projects/${p.id}`} style={{ textDecoration: "none", color: "inherit" }}>
              <div className="card proj-card">
                <div className="proj-thumb"><ProjectArt id={p.id} /></div>
                <div className="proj-body"><h3>{p.title}</h3><p>{p.summary}</p>
                  <div className="proj-meta"><span className="badge badge-track">{p.track}</span><span>by <b>{p.team}</b></span></div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 8 }}>
        <button className="btn-ghost btn-sm" disabled={page <= 1 || loading} onClick={() => load(page - 1)}><I.back /> Prev</button>
        <span style={{ color: "var(--muted)" }}>Page {page}</span>
        <button className="btn-ghost btn-sm" disabled={loading || items.length < 12} onClick={() => load(page + 1)}>Next <I.arrow /></button>
      </div>
    </div>
  );
}
export default function Gallery({ params }: { params: { slug: string } }) { return <Suspense><Inner event={params.slug} /></Suspense>; }
