"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { HeroScene, ProjectArt, I } from "@/components/art";

export default function Home() {
  const [events, setEvents] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [spotlightSlug, setSpotlightSlug] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api("/public/events").then((d) => {
      setEvents(d.events || []);
      const slug = d.events?.[0]?.slug;
      if (slug) {
        setSpotlightSlug(slug);
        api(`/public/events/${slug}/projects?page=1&page_size=6`).then((g) => setProjects(g.projects || [])).catch(() => {});
      }
    }).catch(() => {}).finally(() => setLoaded(true));
  }, []);

  return (
    <div>
      <section className="hero">
        <HeroScene />
        <div className="hero-inner">
          <span className="eyebrow"><span className="dot" /> Self-hosted · Works offline · T1 core</span>
          <h1>Run hackathons on your<br />own infrastructure.</h1>
          <p>Dogfood is a self-hosted platform for managing hackathon events: publish events, form teams with secure invitations, collect submissions before a server-enforced deadline, and present every project in a public gallery. No cloud accounts or external services required.</p>
          <div className="hero-cta">
            <Link href="/organizer?new=1" className="btn">Create New Event <I.arrow /></Link>
            <Link href="/dashboard" className="btn-ghost">Manage My Events</Link>
          </div>
        </div>
        <div className="hero-glassbar">
          <div className="stat"><b>{loaded ? events.length : "…"}</b><span>Published events</span></div>
          <div className="stat"><b>{loaded ? `${projects.length}+` : "…"}</b><span>Showcase projects</span></div>
          <div className="stat"><b>0</b><span>Cloud dependencies</span></div>
          <div className="stat"><b>UTC</b><span>Server-enforced deadlines</span></div>
        </div>
      </section>

      <svg className="wave-sep" viewBox="0 0 1160 46" preserveAspectRatio="none" aria-hidden>
        <path d="M0 26 Q 145 6 290 22 T 580 22 T 870 22 T 1160 22 V46 H0 Z" fill="rgba(255,255,255,.7)" />
      </svg>

      <div className="grid grid-3">
        <div className="card"><h3><I.pin /> Launch</h3><p style={{ color: "var(--muted)" }}>Spin up a new event page in seconds. Set your dates, tracks, and prizes, then publish when you're ready.</p><Link href="/organizer?new=1">Create event <I.arrow /></Link></div>
        <div className="card"><h3><I.team /> Review</h3><p style={{ color: "var(--muted)" }}>Track team formations and monitor project drafts. Ensure all submissions land smoothly before the clock runs out.</p><Link href="/organizer">Review submissions <I.arrow /></Link></div>
        <div className="card"><h3><I.cal /> Run</h3><p style={{ color: "var(--muted)" }}>Configure deadlines, manage participants, and watch the live dashboard as your event unfolds.</p><Link href="/organizer">Organizer console <I.arrow /></Link></div>
      </div>

      <div className="page-head" style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <h2 style={{ margin: 0 }}>Featured submissions</h2>
        {spotlightSlug && <Link href={`/events/${spotlightSlug}/projects`} style={{ marginLeft: "auto" }}>View gallery <I.arrow /></Link>}
      </div>
      <div className="grid grid-3">
        {projects.slice(0, 3).map((p) => (
          <Link key={p.id} href={`/events/${spotlightSlug}/projects/${p.id}`} style={{ textDecoration: "none", color: "inherit" }}>
            <div className="card proj-card">
              <div className="proj-thumb"><ProjectArt id={p.id} /></div>
              <div className="proj-body"><h3>{p.title}</h3><p>{p.summary}</p>
                <div className="proj-meta"><span className="badge badge-track">{p.track}</span><span>by <b>{p.team}</b></span></div>
              </div>
            </div>
          </Link>
        ))}
        {!loaded && [0, 1, 2].map((i) => <div key={i} className="card"><div className="skel" style={{ height: 150 }} /></div>)}
      </div>

      <div className="card" style={{ display: "flex", gap: 18, alignItems: "center", flexWrap: "wrap", background: "linear-gradient(120deg, rgba(255,255,255,.85), rgba(207,244,250,.6))" }}>
        <div style={{ flex: "2 1 280px" }}>
          <h2>Prepared for judging, when you need it.</h2>
          <p style={{ color: "var(--muted)", margin: 0 }}>Judges and scores are stored with clean module boundaries, so a scoring console can be added later without reworking T1.</p>
        </div>
        <Link href="/events" className="btn">Find your event <I.arrow /></Link>
      </div>
    </div>
  );
}
