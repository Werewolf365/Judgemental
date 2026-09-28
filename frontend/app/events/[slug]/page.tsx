"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, fetchMe, fmtDate, useCountdown, type Me } from "@/lib/api";
import { HeroScene, I } from "@/components/art";

function Countdown({ deadline }: { deadline?: string }) {
  const c = useCountdown(deadline);
  if (!c) return null;
  if (c.past) return <span className="badge badge-muted"><span className="pip pip-grey" /> Submissions closed</span>;
  return <span className="countdown">{c.d}d : {String(c.h).padStart(2, "0")}h : {String(c.m).padStart(2, "0")}m : {String(c.s).padStart(2, "0")}s left</span>;
}

/* ─── Registration form fields ─── */
const DEGREE_OPTIONS = [
  "", "B.Tech / B.E.", "B.Sc", "BCA", "M.Tech / M.E.", "M.Sc", "MCA",
  "MBA", "Ph.D.", "Diploma", "Other",
];
const YEAR_OPTIONS = ["", "1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year", "Graduated"];

type RegForm = {
  fullName: string; email: string; phone: string; age: string;
  degree: string; yearOfStudy: string; institution: string;
  dietaryRestrictions: string; tshirtSize: string;
};
const EMPTY_FORM: RegForm = {
  fullName: "", email: "", phone: "", age: "",
  degree: "", yearOfStudy: "", institution: "",
  dietaryRestrictions: "", tshirtSize: "",
};
type RegErrors = Partial<Record<keyof RegForm, string>>;

function validate(f: RegForm): RegErrors {
  const e: RegErrors = {};
  if (!f.fullName.trim()) e.fullName = "Full name is required.";
  if (!f.email.trim()) e.email = "Email is required.";
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)) e.email = "Enter a valid email address.";
  if (!f.phone.trim()) e.phone = "Phone number is required.";
  else if (!/^\+?[\d\s\-()]{7,18}$/.test(f.phone.trim())) e.phone = "Enter a valid phone number.";
  if (!f.age.trim()) e.age = "Age is required.";
  else { const n = Number(f.age); if (!Number.isInteger(n) || n < 13 || n > 120) e.age = "Age must be between 13 and 120."; }
  if (!f.degree) e.degree = "Select your degree / program.";
  if (!f.yearOfStudy) e.yearOfStudy = "Select your year of study.";
  if (!f.institution.trim()) e.institution = "Institution name is required.";
  return e;
}

function FieldErr({ msg }: { msg?: string }) {
  if (!msg) return null;
  return <span className="field-inline-err">{msg}</span>;
}

/* ─── Registration overlay ─── */
function RegistrationOverlay({
  me, onComplete, onCancel,
}: {
  me: Me; onComplete: (data: RegForm) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState<RegForm>({ ...EMPTY_FORM, fullName: me?.display_name || "", email: me?.email || "" });
  const [errors, setErrors] = useState<RegErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [serverErr, setServerErr] = useState("");

  function set<K extends keyof RegForm>(key: K, val: string) {
    setForm((p) => ({ ...p, [key]: val }));
    if (errors[key]) setErrors((p) => { const n = { ...p }; delete n[key]; return n; });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const errs = validate(form);
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setSubmitting(true); setServerErr("");
    try {
      // For now, registration details are stored client-side / forwarded
      // to any future backend endpoint. The primary purpose is gating.
      onComplete(form);
    } catch (err: any) {
      setServerErr(err.message || "Something went wrong.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="reg-overlay" onClick={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div className="reg-panel card field">
        <button type="button" className="reg-close" onClick={onCancel} aria-label="Close">✕</button>

        <span className="eyebrow" style={{ marginBottom: 6 }}><span className="dot" /> Registration</span>
        <h2 style={{ marginTop: 6, marginBottom: 2 }}>Participant details</h2>
        <p className="form-note" style={{ marginBottom: 18 }}>
          Fill out the form below to complete your registration. You'll set up your team in the next step.
        </p>

        {serverErr && <div className="form-error">{serverErr}</div>}

        <form onSubmit={handleSubmit} noValidate>
          {/* Row 1 — Name / Email */}
          <div className="reg-row">
            <div className="reg-col">
              <label htmlFor="reg-fullName">Full name *</label>
              <input id="reg-fullName" value={form.fullName} onChange={(e) => set("fullName", e.target.value)}
                placeholder="Jane Doe" autoFocus className={errors.fullName ? "has-error" : ""} />
              <FieldErr msg={errors.fullName} />
            </div>
            <div className="reg-col">
              <label htmlFor="reg-email">Email *</label>
              <input id="reg-email" type="email" value={form.email} onChange={(e) => set("email", e.target.value)}
                placeholder="jane@example.com" className={errors.email ? "has-error" : ""} />
              <FieldErr msg={errors.email} />
            </div>
          </div>

          {/* Row 2 — Phone / Age */}
          <div className="reg-row">
            <div className="reg-col">
              <label htmlFor="reg-phone">Phone number *</label>
              <input id="reg-phone" type="tel" value={form.phone} onChange={(e) => set("phone", e.target.value)}
                placeholder="+91 98765 43210" className={errors.phone ? "has-error" : ""} />
              <FieldErr msg={errors.phone} />
            </div>
            <div className="reg-col" style={{ maxWidth: 130 }}>
              <label htmlFor="reg-age">Age *</label>
              <input id="reg-age" type="number" min={13} max={120} value={form.age}
                onChange={(e) => set("age", e.target.value)} placeholder="20" className={errors.age ? "has-error" : ""} />
              <FieldErr msg={errors.age} />
            </div>
          </div>

          {/* Row 3 — Degree / Year */}
          <div className="reg-row">
            <div className="reg-col">
              <label htmlFor="reg-degree">Degree / program *</label>
              <select id="reg-degree" value={form.degree} onChange={(e) => set("degree", e.target.value)} className={errors.degree ? "has-error" : ""}>
                <option value="" disabled>Select…</option>
                {DEGREE_OPTIONS.filter(Boolean).map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
              <FieldErr msg={errors.degree} />
            </div>
            <div className="reg-col">
              <label htmlFor="reg-year">Year of study *</label>
              <select id="reg-year" value={form.yearOfStudy} onChange={(e) => set("yearOfStudy", e.target.value)} className={errors.yearOfStudy ? "has-error" : ""}>
                <option value="" disabled>Select…</option>
                {YEAR_OPTIONS.filter(Boolean).map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <FieldErr msg={errors.yearOfStudy} />
            </div>
          </div>

          {/* Row 4 — Institution (full-width) */}
          <label htmlFor="reg-institution">Institution / college *</label>
          <input id="reg-institution" value={form.institution} onChange={(e) => set("institution", e.target.value)}
            placeholder="Indian Institute of Technology Bombay" className={errors.institution ? "has-error" : ""} />
          <FieldErr msg={errors.institution} />

          {/* Row 5 — T-shirt */}
          <label htmlFor="reg-tshirt">T-shirt size</label>
          <select id="reg-tshirt" value={form.tshirtSize} onChange={(e) => set("tshirtSize", e.target.value)}>
            <option value="">N/A</option>
            {["XS", "S", "M", "L", "XL", "XXL"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <p className="form-note" style={{ marginTop: 8 }}>
            Which track will you compete in? Nothing to pick here — your team chooses
            one track when it creates its project, so every teammate is on the same track by construction.
          </p>

          {/* Row 6 — Dietary */}
          <label htmlFor="reg-dietary">Dietary restrictions</label>
          <input id="reg-dietary" value={form.dietaryRestrictions} onChange={(e) => set("dietaryRestrictions", e.target.value)}
            placeholder="None, Vegetarian, Vegan, Gluten-free…" />

          <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
            <button type="submit" className="btn" disabled={submitting}>{submitting ? "Submitting…" : "Continue to team setup"} <I.arrow /></button>
            <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ─── Main page ─── */
export default function EventPage({ params }: { params: { slug: string } }) {
  const [data, setData] = useState<any>(null);
  const [me, setMe] = useState<Me>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [joined, setJoined] = useState(false);
  const [showRegForm, setShowRegForm] = useState(false);
  const [isDraftPreview, setIsDraftPreview] = useState(false);
  // Organizers, admins and judges run events; they never compete in one, so
  // the server refuses their registration. Mirror that here rather than
  // offering a form that is guaranteed to bounce.
  const [isStaff, setIsStaff] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const m = await fetchMe();
      if (cancelled) return;
      setMe(m);
      const isStaff = !!m && (m.role === "ORGANIZER" || m.role === "ADMIN" || m.role === "JUDGE");
      setIsStaff(isStaff);
      try {
        const d = await api(`/public/events/${params.slug}`);
        if (cancelled) return;
        setData(d);
        api(`/events/${d.event.id}/membership`).then((mm) => setJoined(mm.joined)).catch(() => {});
      } catch {
        // Drafts are hidden publicly — organizers/admins still get a preview.
        if (!isStaff) { setMsg("This event doesn't exist or isn't published yet."); setFailed(true); return; }
        try {
          const d = await api(`/events/${params.slug}`);
          const [t, p] = await Promise.all([
            api(`/events/${d.event.id}/tracks`).catch(() => ({ tracks: [] })),
            api(`/events/${d.event.id}/prizes`).catch(() => ({ prizes: [] })),
          ]);
          if (cancelled) return;
          setData({ event: d.event, tracks: t.tracks || [], prizes: p.prizes || [] });
          setIsDraftPreview(true);
          api(`/events/${d.event.id}/membership`).then((mm) => setJoined(mm.joined)).catch(() => {});
        } catch (e: any) { if (!cancelled) { setMsg(e.message); setFailed(true); } }
      }
    })();
    return () => { cancelled = true; };
  }, [params.slug]);

  /* Step 1: clicking "Join" opens the form (if not logged in, redirect to login first) */
  function handleJoinClick() {
    if (!me) { window.location.href = "/login"; return; }
    if (isStaff) { setMsg("Your role runs events rather than competing in them, so there is nothing to register for."); return; }
    setShowRegForm(true);
  }

  /* Step 2: after form submit, call the existing join API then route to dashboard for team creation */
  async function completeRegistration(regData: RegForm) {
    setBusy(true); setMsg(""); setShowRegForm(false);
    try {
      await api(`/events/${data.event.id}/join`, { method: "POST", body: JSON.stringify(regData) });
      setJoined(true);
      setMsg("Registration complete! Redirecting to your workspace to create a team…");
      // Give the user a moment to read the message, then redirect to dashboard
      // with the event preselected for team creation.
      setTimeout(() => { window.location.href = `/dashboard?event=${data.event.id}`; }, 1200);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  async function leave() {
    if (!confirm("Leave this event? You must leave your team first if you're on one.")) return;
    setBusy(true); setMsg("");
    try { await api(`/events/${data.event.id}/join`, { method: "DELETE" }); setJoined(false); setMsg("You've left the event."); }
    catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  if (!data) return failed
    ? <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
        <h1>Event not found</h1><p>{msg || "This event doesn't exist or isn't published yet."}</p>
        <Link href="/events" className="btn">Browse events</Link></div>
    : <div className="card"><div className="skel" style={{ height: 160 }} /></div>;
  const ev = data.event;
  return (
    <div>
      {showRegForm && !isStaff && (
        <RegistrationOverlay me={me} onComplete={completeRegistration} onCancel={() => setShowRegForm(false)} />
      )}
      <div className="hero" style={{ paddingBottom: 0 }}>
        <HeroScene />
        <div className="hero-inner">
          <span className={`badge ${isDraftPreview ? "badge-warn" : "badge-ok"}`}><span className={`pip ${isDraftPreview ? "pip-amber" : "pip-green"}`} /> {isDraftPreview ? "Draft preview — organizers only" : "Published event"}</span>
          <h1 style={{ marginTop: 10 }}>{ev.name}</h1>
          <p>{ev.description || "A Dogfood hackathon event."}</p>
          <div className="hero-cta">
            {isStaff ? (
              <span className="badge badge-track" title="Organizers, admins and judges run events instead of competing in them.">
                <I.team /> {me?.role} — you run events, not compete in them
              </span>
            ) : (
              <button className="btn" onClick={handleJoinClick} disabled={busy || joined}>{busy ? "Joining…" : joined ? "You're registered" : me ? "Join this event" : "Log in to join"} <I.arrow /></button>
            )}
            {joined && <button className="btn-ghost" onClick={leave} disabled={busy}>Leave event</button>}
            <Link href={`/events/${ev.slug}/projects`} className="btn-ghost">View submissions</Link>
            {ev.voting_enabled && (
              <Link href={`/events/${ev.slug}/vote`} className="btn-ghost">Vote for projects</Link>
            )}
            {ev.gallery_visibility && ev.gallery_visibility !== "PUBLIC" && (
              <span className="badge badge-muted" title="Set by the organizer">Gallery: {ev.gallery_visibility === "PARTICIPANTS" ? "Participants" : "Organizers only"}</span>
            )}
          </div>
          {msg && <p style={{ color: "var(--sea-800)", fontWeight: 600 }}>{msg}</p>}
        </div>
        <div className="hero-glassbar"><I.clock />
          <div><b>Submission deadline</b><div className="countdown"><Countdown deadline={ev.submissions_close} /></div>
          <div style={{ color: "var(--muted)", fontSize: 13.5 }}>closes {fmtDate(ev.submissions_close)} · enforced by the server clock</div></div>
        </div>
      </div>
      <div className="grid grid-2">
        <div className="card"><h2>Tracks</h2>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{data.tracks.map((t: any) => <span key={t.id} className="badge badge-track">{t.name}</span>)}</div>
          <h2 style={{ marginTop: 18 }}><I.cal /> Key dates</h2>
          <dl className="kv"><dt>Registration</dt><dd>{fmtDate(ev.registration_start)} → {fmtDate(ev.registration_close)}</dd>
            <dt>Event</dt><dd>{fmtDate(ev.event_start)} → {fmtDate(ev.event_end)}</dd>
            <dt>Submissions</dt><dd>{fmtDate(ev.submissions_open)} → <b>{fmtDate(ev.submissions_close)}</b></dd></dl>
        </div>
        <div className="card"><h2><I.trophy /> Prizes</h2>
          {!data.prizes.length && <p style={{ color: "var(--muted)" }}>Prizes will be announced soon.</p>}
          {data.prizes.map((p: any) => <div key={p.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}><b>{p.name}</b><div style={{ color: "var(--muted)", fontSize: 14 }}>{p.description}{p.value_desc ? ` · ${p.value_desc}` : ""}</div></div>)}
        </div>
      </div>
    </div>
  );
}
