"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, fetchMe, fmtDate } from "@/lib/api";
import { I } from "@/components/art";
import DateTimePicker from "@/components/DateTimePicker";
import JudgingPanel from "@/components/JudgingPanel";
import Popup from "@/components/Popup";

const STEPS = [
  { n: 1, key: "details", label: "Details" },
  { n: 2, key: "tracks", label: "Tracks" },
  { n: 3, key: "prizes", label: "Prizes" },
  { n: 4, key: "form", label: "Submission form" },
  { n: 5, key: "gallery", label: "Gallery access" },
  { n: 6, key: "publish", label: "Review & publish" },
  { n: 7, key: "voting", label: "Voting" },
] as const;
type StepKey = typeof STEPS[number]["key"];

const FIELD_TYPES = [
  { v: "text", label: "Short text" },
  { v: "textarea", label: "Long text" },
  { v: "number", label: "Number" },
  { v: "url", label: "Link" },
  { v: "select", label: "Dropdown" },
];

const VIS_OPTIONS = [
  { v: "PUBLIC", title: "Public", desc: "Anyone on the internet can browse the gallery." },
  { v: "PARTICIPANTS", title: "Participants", desc: "Only registered participants and organizers." },
  { v: "ORGANIZERS_ONLY", title: "Organizers only", desc: "Hidden from everyone except organizers and admins." },
];

function Console() {
  const [me, setMe] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [sel, setSel] = useState<string>("");
  const [detail, setDetail] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [step, setStep] = useState<StepKey>("details");
  // create form
  const [name, setName] = useState("");
  const [close, setClose] = useState("");
  // details edit form
  const [eName, setEName] = useState("");
  const [eDesc, setEDesc] = useState("");
  const [eClose, setEClose] = useState("");
  const [trackName, setTrackName] = useState("");
  const [prize, setPrize] = useState({ name: "", description: "", value_desc: "" });
  const [subs, setSubs] = useState<any[]>([]);
  const [subFilter, setSubFilter] = useState("");
  const [people, setPeople] = useState<any[]>([]);
  const [reviewTab, setReviewTab] = useState<"submissions" | "people" | "team">("submissions");
  const [orgs, setOrgs] = useState<any[]>([]);
  const [orgEmail, setOrgEmail] = useState("");
  const [formFields, setFormFields] = useState<any[]>([]);
  const [newField, setNewField] = useState({ label: "", field_type: "text", required: false, optionsText: "" });
  const [editingId, setEditingId] = useState("");
  const [editField, setEditField] = useState({ label: "", field_type: "text", required: false, optionsText: "" });
  // voting step
  const [voting, setVoting] = useState<any>(null);
  const [vClose, setVClose] = useState("");
  const [turnout, setTurnout] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [auditQ, setAuditQ] = useState("");
  // One-shot confirmation after a publish, so the moment of going live is
  // unmistakable rather than a line of text that scrolls past.
  const [notice, setNotice] = useState<{ title: string; body: React.ReactNode } | null>(null);
  const router = useRouter();
  const search = useSearchParams();
  const wanted = search.get("event");
  // /organizer?new=1 is the landing-page "Create New Event" target: open Step 1
  // on the create form instead of pre-selecting the most recent event.
  const startNew = search.get("new") === "1";

  async function loadDetail(id: string) {
    try { setDetail(await api(`/public/events/${id}`)); }
    catch {
      try {
        const d = await api(`/events/${id}`);
        const [t, p] = await Promise.all([
          api(`/events/${d.event.id}/tracks`).catch(() => ({ tracks: [] })),
          api(`/events/${d.event.id}/prizes`).catch(() => ({ prizes: [] })),
        ]);
        setDetail({ event: d.event, tracks: t.tracks || [], prizes: p.prizes || [] });
      } catch { setDetail(null); setFormFields([]); setVoting(null); return; }
    }
    try {
      const ff = await api(`/events/${id}/form-fields`);
      setFormFields(ff.fields || []);
    } catch { setFormFields([]); }
    await loadVoting(id);
  }

  async function loadVoting(id: string) {
    try {
      const v = await api(`/events/${id}/voting`);
      setVoting(v.config);
      setVClose(v.config.voting_close ? v.config.voting_close.slice(0, 16) : "");
      setTurnout(v.turnout);
    } catch { setVoting(null); }
  }

  async function saveVoting(patch: any) {
    if (!detail) return;
    setMsg("");
    try {
      const d = await api(`/events/${detail.event.id}/voting`,
        { method: "PATCH", body: JSON.stringify(patch) });
      setVoting(d.config);
      setMsg("Voting settings saved.");
      await loadVoting(detail.event.id);
    } catch (e: any) { setMsg(e.message); }
  }

  async function loadAudit() {
    if (!detail) return;
    try {
      const d = await api(`/events/${detail.event.id}/audit?q=${encodeURIComponent(auditQ)}&limit=100`);
      setAudit(d.entries || []);
    } catch (e: any) { setMsg(e.message); }
  }

  async function loadEvents(selectId?: string) {
    const d = await api("/events").catch(() => null)
      || await api("/public/events").catch(() => ({ events: [] }));
    const list = d.events || [];
    setEvents(list);
    const want = selectId || wanted;
    if (want && list.some((e: any) => e.id === want || e.slug === want)) setSel(want);
    else if (!selectId && !startNew && list[0]) setSel((s) => s || list[0].id);
  }

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      if (m.role !== "ORGANIZER" && m.role !== "ADMIN") { setMsg("Organizer or Admin role required."); return; }
      setMe(m); loadEvents();
    })();
  }, [router]);
  useEffect(() => { if (sel) loadDetail(sel); }, [sel, events]);

  // Keep the edit form in sync with the working event.
  useEffect(() => {
    if (!detail?.event) return;
    setEName(detail.event.name || "");
    setEDesc(detail.event.description || "");
    setEClose(detail.event.submissions_close ? detail.event.submissions_close.slice(0, 16) : "");
  }, [detail?.event?.id]);

  async function loadReview(id: string) {
    try { setSubs((await api(`/events/${id}/submissions?status=${subFilter}`)).submissions || []); } catch { setSubs([]); }
    try { setPeople((await api(`/events/${id}/participants`)).participants || []); } catch { setPeople([]); }
    try { setOrgs((await api(`/events/${id}/organizers`)).organizers || []); } catch { setOrgs([]); }
  }
  useEffect(() => { if (sel) loadReview(sel); }, [sel, subFilter]);

  async function addOrganizer(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    const email = orgEmail.trim();
    if (!email) { setMsg("Enter the organizer's email."); return; }
    try {
      const d = await api(`/events/${sel}/organizers`, { method: "POST", body: JSON.stringify({ email }) });
      setOrgEmail("");
      setMsg(`${d.organizer.display_name} can now manage this event.`);
      await loadReview(sel);
    } catch (e: any) { setMsg(e.message); }
  }
  async function removeOrganizer(userId: string) {
    setMsg("");
    try {
      await api(`/events/${sel}/organizers/${userId}`, { method: "DELETE" });
      setMsg("Organizer removed from this event.");
      await loadReview(sel);
    } catch (e: any) { setMsg(e.message); }
  }

  async function create() {
    setMsg("");
    if (!name.trim()) { setMsg("Give the event a name."); return; }
    try {
      const d = await api("/events", { method: "POST", body: JSON.stringify({ name: name.trim(), submissions_close: close || new Date(Date.now() + 30 * 864e5).toISOString() }) });
      setName(""); setClose("");
      setMsg(`Draft “${d.event.name}” created — Step 1 of 7 done. Add tracks next.`);
      await loadEvents(d.event.id);
      setStep("tracks");
    } catch (e: any) { setMsg(e.message); }
  }

  async function saveDetails() {
    if (!detail) return;
    setMsg("");
    try {
      const d = await api(`/events/${detail.event.id}`, { method: "PATCH", body: JSON.stringify({ name: eName.trim(), description: eDesc, submissions_close: eClose || null }) });
      setMsg("Details saved.");
      await loadEvents(d.event.id);
      await loadDetail(d.event.id);
    } catch (e: any) { setMsg(e.message); }
  }

  async function addTrack() {
    if (!trackName.trim() || !detail) return;
    try { await api(`/events/${detail.event.id}/tracks`, { method: "POST", body: JSON.stringify({ name: trackName.trim() }) }); setTrackName(""); await loadDetail(detail.event.id); }
    catch (e: any) { setMsg(e.message); }
  }
  async function addPrize() {
    if (!prize.name.trim() || !detail) return;
    try { await api(`/events/${detail.event.id}/prizes`, { method: "POST", body: JSON.stringify(prize) }); setPrize({ name: "", description: "", value_desc: "" }); await loadDetail(detail.event.id); }
    catch (e: any) { setMsg(e.message); }
  }
  function parseOptions(text: string) {
    return text.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
  }
  async function addField() {
    if (!newField.label.trim() || !detail) return;
    try {
      await api(`/events/${detail.event.id}/form-fields`, { method: "POST", body: JSON.stringify({
        label: newField.label.trim(), field_type: newField.field_type,
        required: newField.required, options: parseOptions(newField.optionsText),
      }) });
      setNewField({ label: "", field_type: "text", required: false, optionsText: "" });
      await loadDetail(detail.event.id);
    } catch (e: any) { setMsg(e.message); }
  }
  function startEdit(f: any) {
    setEditingId(f.id);
    setEditField({ label: f.label, field_type: f.field_type, required: !!f.required, optionsText: (f.options || []).join(", ") });
  }
  async function saveEdit(id: string) {
    if (!editField.label.trim()) { setMsg("Field label is required."); return; }
    try {
      await api(`/form-fields/${id}`, { method: "PATCH", body: JSON.stringify({
        label: editField.label.trim(), field_type: editField.field_type,
        required: editField.required, options: parseOptions(editField.optionsText),
      }) });
      setEditingId("");
      await loadDetail(detail.event.id);
    } catch (e: any) { setMsg(e.message); }
  }
  async function deleteField(id: string) {
    if (!confirm("Remove this field from the submission form? Already-saved answers stay on existing projects.")) return;
    try { await api(`/form-fields/${id}`, { method: "DELETE" }); await loadDetail(detail.event.id); }
    catch (e: any) { setMsg(e.message); }
  }
  async function toggleFieldRequired(f: any) {
    try {
      await api(`/form-fields/${f.id}`, { method: "PATCH", body: JSON.stringify({
        label: f.label, field_type: f.field_type, required: !f.required, options: f.options || [],
      }) });
      await loadDetail(detail.event.id);
    } catch (e: any) { setMsg(e.message); }
  }
  async function setGalleryVis(v: string) {
    if (!detail) return;
    try {
      await api(`/events/${detail.event.id}`, { method: "PATCH", body: JSON.stringify({ gallery_visibility: v }) });
      await loadDetail(detail.event.id);
      setMsg(`Gallery access set to “${VIS_OPTIONS.find((o) => o.v === v)?.title}”.`);
    } catch (e: any) { setMsg(e.message); }
  }
  async function toggleVisibility(id: string, visible: boolean) {
    try {
      await api(`/submissions/${id}/visibility`, { method: "POST", body: JSON.stringify({ visible }) });
      if (sel) loadReview(sel);
    } catch (e: any) { setMsg(e.message); }
  }
  async function publish(un: boolean) {
    const id = detail?.event?.id || sel;
    if (!id) { setMsg("Create an event first."); return; }
    try {
      const d = await api(`/events/${id}/${un ? "unpublish" : "publish"}`, { method: "POST", body: "{}" });
      setMsg(un ? "Moved back to draft — hidden from Events and the Gallery." : `“${d.event.name}” is live in Events and the Gallery.`);
      if (un) {
        setNotice({ title: "Moved back to draft", body: `“${d.event.name}” is hidden from Events and the gallery again.` });
      } else {
        setNotice({
          title: "Event published",
          body: <>“{d.event.name}” is now live. It appears in the <b>Events</b> list, and anyone who has the
            link can open <code>/events/{d.event.slug}</code> and join.</>,
        });
      }
      await loadEvents(d.event.id);
      await loadDetail(d.event.id);
    } catch (e: any) { setMsg(e.message); }
  }

  if (!me && !msg) return <div className="card">Loading console…</div>;
  if (msg && !me) return <div className="card empty"><h3>Access restricted</h3><p>{msg}</p><p className="form-note">Log in as organizer@local.test to manage events.</p></div>;

  const ev = detail?.event;
  const curVis = (ev?.gallery_visibility || "PUBLIC").toUpperCase();
  const stepN = STEPS.find((s) => s.key === step)!.n;
  const goStep = (key: StepKey) => { setMsg(""); setStep(key); };
  const slug = ev?.slug || sel;

  return (
    <div>
      {notice && (
        <Popup kind={notice.title.startsWith("Moved") ? "info" : "ok"} title={notice.title}
          dismissLabel="Got it" onClose={() => setNotice(null)}>
          {notice.body}
        </Popup>
      )}
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Organizer</span><h1>Event console</h1>
        <p className="lead">Seven steps, in order: details, tracks, prizes, submission form, gallery access, publish, then voting.</p></div>

      {/* Working event bar */}
      <div className="card field" style={{ padding: "14px 22px" }}>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ flex: "2 1 240px" }}><label>Working event</label>
            <select value={sel} onChange={(e) => setSel(e.target.value)} style={{ marginBottom: 0 }}>
              {events.map((e) => <option key={e.id} value={e.id}>{e.name} ({e.status})</option>)}
            </select></div>
          {slug && <a className="btn-ghost btn-sm" href={`/events/${slug}/projects`}>View gallery</a>}
          <button className="btn-ghost btn-sm" onClick={() => { setSel(""); setStep("details"); setDetail(null); }}>+ New event</button>
        </div>
      </div>

      {/* Setup wizard */}
      <div className="card field">
        <div className="steps" aria-label="Setup progress">
          {STEPS.map((s) => (
            <button key={s.key} type="button" onClick={() => goStep(s.key)}
              className={`step ${s.n < stepN || (s.key === "publish" && ev?.status === "PUBLISHED") ? "done" : s.n === stepN ? "now" : ""}`}
              style={{ background: "none", borderLeft: 0, borderRight: 0, borderBottom: 0, cursor: "pointer", textAlign: "left", font: "inherit" }}>
              <b><span className="n">{s.n < stepN ? "✓" : s.n}</span> {s.label}</b>
              {s.key === "details" && ev ? ev.name : s.key === "tracks" && ev ? `${detail?.tracks?.length || 0} added` : s.key === "prizes" && ev ? `${detail?.prizes?.length || 0} added` : s.key === "form" && ev ? `${formFields.length} fields` : s.key === "gallery" && ev ? VIS_OPTIONS.find((o) => o.v === curVis)?.title : s.key === "publish" && ev ? ev.status : s.key === "voting" && voting ? (voting.voting_enabled ? `On · ${voting.voting_mode}` : "Off") : ""}
            </button>
          ))}
        </div>
        {msg && <p>{msg}</p>}

        {step === "details" && (
          <div>{!ev ? (
            <div style={{ maxWidth: 560 }}><h2>Step 1 — Name your event</h2>
              <label>Event name</label><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Spring Hack 2027" />
              <label>Submissions close (UTC)</label><DateTimePicker value={close} onChange={setClose} placeholder="Pick deadline date & time" defaultToday />
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn" onClick={create}>Create draft <I.arrow /></button>
              </div></div>
          ) : (
            <div style={{ maxWidth: 560 }}><h2>Step 1 — Event details</h2>
              <label>Event name</label><input value={eName} onChange={(e) => setEName(e.target.value)} />
              <label>Description</label><textarea value={eDesc} onChange={(e) => setEDesc(e.target.value)} placeholder="What is this hackathon about?" />
              <label>Submissions close (UTC)</label><DateTimePicker value={eClose} onChange={setEClose} placeholder="Pick deadline date & time" defaultToday />
              <div style={{ display: "flex", gap: 10 }}>
                <button className="btn-ghost" onClick={saveDetails}>Save details</button>
                <button className="btn" onClick={() => goStep("tracks")}>Continue to tracks <I.arrow /></button>
              </div></div>
          )}</div>
        )}

        {step === "tracks" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 2 — Tracks ({detail?.tracks?.length || 0})</h2>
            <p style={{ color: "var(--muted)" }}>Categories participants submit into. You can add more later.</p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
              {(detail?.tracks || []).map((t: any) => <span key={t.id} className="badge badge-track">{t.name}</span>)}
            </div>
            <div style={{ display: "flex", gap: 8 }}><input value={trackName} onChange={(e) => setTrackName(e.target.value)} placeholder="New track name" style={{ flex: 1 }} />
              <button className="btn" onClick={addTrack}>Add track</button></div>
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn-ghost" onClick={() => goStep("details")}><I.back /> Back</button>
              <button className="btn" onClick={() => goStep("prizes")}>Continue to prizes <I.arrow /></button>
            </div></>)}</div>
        )}

        {step === "prizes" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 3 — Prizes ({detail?.prizes?.length || 0})</h2>
            <p style={{ color: "var(--muted)" }}>Optional, but every professional event page shows them.</p>
            {(detail?.prizes || []).map((p: any) => <div key={p.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}><b>{p.name}</b> <span style={{ color: "var(--muted)" }}>{p.description}</span></div>)}
            <div className="grid grid-3" style={{ marginTop: 10 }}>
              <input placeholder="Prize name" value={prize.name} onChange={(e) => setPrize({ ...prize, name: e.target.value })} />
              <input placeholder="Description" value={prize.description} onChange={(e) => setPrize({ ...prize, description: e.target.value })} />
              <input placeholder="Value / award" value={prize.value_desc} onChange={(e) => setPrize({ ...prize, value_desc: e.target.value })} />
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
              <button className="btn" onClick={addPrize}>Add prize</button>
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn-ghost" onClick={() => goStep("tracks")}><I.back /> Back</button>
              <button className="btn" onClick={() => goStep("form")}>Continue to submission form <I.arrow /></button>
            </div></>)}</div>
        )}

        {step === "form" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 4 — Submission form ({formFields.length})</h2>
            <p style={{ color: "var(--muted)" }}>Extra questions every team answers when submitting. Everything here is editable — change labels, types, requirements, or remove fields entirely.</p>
            {!formFields.length && <p style={{ color: "var(--muted)" }}>No custom questions yet. Projects always ask for title, summary, description, links and track.</p>}
            {formFields.map((f: any) => (
              <div key={f.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
                {editingId === f.id ? (
                  <div className="grid grid-3" style={{ gap: 8 }}>
                    <input aria-label="Field label" value={editField.label} onChange={(e) => setEditField({ ...editField, label: e.target.value })} placeholder="Question" />
                    <select aria-label="Field type" value={editField.field_type} onChange={(e) => setEditField({ ...editField, field_type: e.target.value })}>
                      {FIELD_TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
                    </select>
                    <input aria-label="Options, comma separated" value={editField.optionsText} onChange={(e) => setEditField({ ...editField, optionsText: e.target.value })} placeholder="Options (dropdown only, comma separated)" />
                    <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13.5 }}>
                      <input type="checkbox" checked={editField.required} onChange={(e) => setEditField({ ...editField, required: e.target.checked })} /> Required
                    </label>
                    <span style={{ display: "flex", gap: 8 }}>
                      <button className="btn btn-sm" onClick={() => saveEdit(f.id)}>Save</button>
                      <button className="btn-ghost btn-sm" onClick={() => setEditingId("")}>Cancel</button>
                    </span>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                    <div><b>{f.label}</b>
                      <div style={{ fontSize: 13, color: "var(--muted)" }}>{FIELD_TYPES.find((t) => t.v === f.field_type)?.label}{f.field_type === "select" ? `: ${(f.options || []).join(", ")}` : ""}</div></div>
                    {f.required && <span className="badge badge-warn">Required</span>}
                    <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
                      <button className="btn-ghost btn-sm" onClick={() => toggleFieldRequired(f)}>{f.required ? "Make optional" : "Make required"}</button>
                      <button className="btn-ghost btn-sm" onClick={() => startEdit(f)}>Edit</button>
                      <button className="link-btn" onClick={() => deleteField(f.id)}>Remove</button>
                    </span>
                  </div>
                )}
              </div>
            ))}
            <h3 style={{ marginTop: 14 }}>Add a question</h3>
            <div className="grid grid-3" style={{ gap: 8 }}>
              <input aria-label="New question" value={newField.label} onChange={(e) => setNewField({ ...newField, label: e.target.value })} placeholder="e.g. Demo video link" />
              <select aria-label="New field type" value={newField.field_type} onChange={(e) => setNewField({ ...newField, field_type: e.target.value })}>
                {FIELD_TYPES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
              </select>
              <input aria-label="New field options" value={newField.optionsText} onChange={(e) => setNewField({ ...newField, optionsText: e.target.value })} placeholder="Options (dropdown only, comma separated)" />
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 10, alignItems: "center", flexWrap: "wrap" }}>
              <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 14 }}>
                <input type="checkbox" checked={newField.required} onChange={(e) => setNewField({ ...newField, required: e.target.checked })} /> Required to submit
              </label>
              <button className="btn" onClick={addField}>Add question</button>
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn-ghost" onClick={() => goStep("prizes")}><I.back /> Back</button>
              <button className="btn" onClick={() => goStep("gallery")}>Continue to gallery access <I.arrow /></button>
            </div></>)}</div>
        )}

        {step === "gallery" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 5 — Who can browse the gallery?</h2>
            <p style={{ color: "var(--muted)" }}>Drafts are always organizers-only. Once published, this setting decides who else gets in.</p>
            <div className="grid grid-3">
              {VIS_OPTIONS.map((o) => (
                <button key={o.v} type="button" onClick={() => setGalleryVis(o.v)}
                  className="card" style={{ margin: 0, cursor: "pointer", textAlign: "left",
                    outline: curVis === o.v ? "2px solid var(--aqua)" : undefined }}>
                  <b>{o.title}</b>
                  <div style={{ fontSize: 13.5, color: "var(--muted)" }}>{o.desc}</div>
                  {curVis === o.v && <div style={{ marginTop: 8 }}><span className="badge badge-ok"><span className="pip pip-green" /> Selected</span></div>}
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn-ghost" onClick={() => goStep("form")}><I.back /> Back</button>
              <button className="btn" onClick={() => goStep("publish")}>Continue to publish <I.arrow /></button>
            </div></>)}</div>
        )}

        {step === "publish" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 6 — Review & publish</h2>
            <p>Status: <span className={`badge ${ev.status === "PUBLISHED" ? "badge-ok" : "badge-muted"}`}>{ev.status}</span></p>
            <dl className="kv">
              <dt>Details</dt><dd>{ev.name} · closes {fmtDate(ev.submissions_close)}</dd>
              <dt>Tracks</dt><dd>{detail?.tracks?.length || 0}</dd>
              <dt>Prizes</dt><dd>{detail?.prizes?.length || 0}</dd>
              <dt>Gallery</dt><dd>{VIS_OPTIONS.find((o) => o.v === curVis)?.title} — {VIS_OPTIONS.find((o) => o.v === curVis)?.desc}</dd>
            </dl>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className="btn" onClick={() => publish(false)}>Publish event <I.arrow /></button>
              <button className="btn-ghost" onClick={() => publish(true)}>Unpublish</button>
              <a className="btn-ghost btn-sm" href={`/events/${ev.slug || ev.id}`}>Preview event page</a>
              <a className="btn-ghost btn-sm" href={`/events/${ev.slug || ev.id}/projects`}>View gallery</a>
            </div>
            <div style={{ marginTop: 14 }}>
              <button className="btn-ghost btn-sm" onClick={() => goStep("gallery")}><I.back /> Back to gallery access</button>{" "}
              <button className="btn btn-sm" onClick={() => goStep("voting")}>Continue to voting <I.arrow /></button>
            </div></>)}</div>
        )}
        {step === "voting" && (
          <div>{!ev ? <p style={{ color: "var(--muted)" }}>Create an event first (Step 1).</p> : (
          <><h2>Step 7 — Community voting</h2>
            <p style={{ color: "var(--muted)" }}>Every voter gets 10 votes to spread across projects. Piling votes onto one project counts for less than broad support, and results stay hidden until the deadline passes.</p>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14.5 }}>
              <input type="checkbox" checked={!!voting?.voting_enabled} style={{ width: "auto", margin: 0 }}
                onChange={(e) => saveVoting({ voting_enabled: e.target.checked })} /> Accept public votes for this event
            </label>
            {voting?.voting_enabled && (
              <>
                <h3>Who may vote?</h3>
                <div className="grid grid-3">
                  {[{ v: "open", title: "Open link", desc: "Anyone with the link. Weakest identity — duplicates are flagged, not blocked." },
                    { v: "email", title: "Email-gated", desc: "One ballot set per email address." },
                    { v: "auth", title: "Authenticated", desc: "Logged-in users only. Can block own-team votes." }].map((o) => (
                    <button key={o.v} type="button" onClick={() => saveVoting({ voting_mode: o.v })}
                      className="card" style={{ margin: 0, cursor: "pointer", textAlign: "left",
                        outline: voting?.voting_mode === o.v ? "2px solid var(--aqua)" : undefined }}>
                      <b>{o.title}</b>
                      <div style={{ fontSize: 13.5, color: "var(--muted)" }}>{o.desc}</div>
                      {voting?.voting_mode === o.v && <div style={{ marginTop: 8 }}><span className="badge badge-ok"><span className="pip pip-green" /> Selected</span></div>}
                    </button>
                  ))}
                </div>
                <div style={{ maxWidth: 560, marginTop: 12 }}>
                  <label>Voting ends (UTC) — blank means open-ended</label>
                  <DateTimePicker value={vClose} onChange={setVClose} placeholder="No closing deadline" defaultToday />
                  <div style={{ marginTop: 8 }}><button className="btn-ghost btn-sm" onClick={() => saveVoting({ voting_close: vClose || null })}>Save deadline</button></div>
                </div>
                <h3>Comments</h3>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {[["public", "Public — everyone sees comments"], ["team", "Team-only — only each project's team (and organizers)"]].map(([v, label]) => (
                    <button key={v} type="button" className={voting?.comments_visibility === v ? "btn btn-sm" : "btn-ghost btn-sm"}
                      onClick={() => saveVoting({ comments_visibility: v })}>{label}</button>
                  ))}
                </div>
                <h3>Turnout</h3>
                {turnout
                  ? <p style={{ color: "var(--muted)" }}>{turnout.voters} voter{turnout.voters === 1 ? "" : "s"} · {turnout.ballots} ballot{turnout.ballots === 1 ? "" : "s"}{turnout.fp_collisions?.length ? ` · ${turnout.fp_collisions.length} shared-device signal${turnout.fp_collisions.length === 1 ? "" : "s"} under review` : " · no duplicate signals"}</p>
                  : <p style={{ color: "var(--muted)" }}>No votes yet.</p>}
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                  <a className="btn-ghost btn-sm" href={`/events/${ev.slug || ev.id}/vote`}>Open ballot box</a>
                  <button className="btn-ghost btn-sm" onClick={() => loadVoting(ev.id)}>Refresh</button>
                </div>
                <h3>Event audit trail</h3>
                <p style={{ color: "var(--muted)", fontSize: 13.5 }}>Every security-relevant action on this event — votes, refusals, moderation — readable here, no database client needed.</p>
                <div style={{ display: "flex", gap: 8 }}>
                  <input value={auditQ} onChange={(e) => setAuditQ(e.target.value)} placeholder="Filter actions, emails…" style={{ flex: 1 }} />
                  <button className="btn-ghost btn-sm" onClick={loadAudit}>Search audit</button>
                </div>
                {!audit.length && <p style={{ color: "var(--muted)" }}>No matching entries — search to load.</p>}
                {audit.map((a: any) => (
                  <div key={a.id} style={{ padding: "6px 0", borderTop: "1px solid var(--line)", fontSize: 13.5 }}>
                    <b className="mono">{a.action}</b> <span style={{ color: "var(--muted)" }}>{a.actor_email || "anonymous"} · {a.created_at ? new Date(a.created_at).toLocaleString() : ""}{a.ip ? ` · ${a.ip}` : ""}</span>
                  </div>))}
              </>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn-ghost" onClick={() => goStep("publish")}><I.back /> Back</button>
            </div></>)}</div>
        )}
      </div>

      {/* Judging console */}
      {ev && <JudgingPanel eventId={ev.id} />}

      {/* Activity review */}
      {ev && (
        <div className="card field">
          <div className="tabs">
            <button className={reviewTab === "submissions" ? "on" : ""} onClick={() => { setReviewTab("submissions"); loadReview(ev.id); }}>Submissions ({subs.length})</button>
            <button className={reviewTab === "people" ? "on" : ""} onClick={() => { setReviewTab("people"); loadReview(ev.id); }}>Participants ({people.length})</button>
            <button className={reviewTab === "team" ? "on" : ""} onClick={() => { setReviewTab("team"); loadReview(ev.id); }}>Organizers ({orgs.length})</button>
            <button className="btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => loadReview(ev.id)}>Refresh</button>
          </div>
          {reviewTab === "submissions" && (
            <div>
              <select value={subFilter} onChange={(e) => setSubFilter(e.target.value)} style={{ maxWidth: 220 }}>
                <option value="">All statuses</option>
                <option value="DRAFT">Drafts</option>
                <option value="SUBMITTED">Submitted</option>
              </select>
              {!subs.length && <p style={{ color: "var(--muted)" }}>No submissions match this filter.</p>}
              {subs.map((s: any) => (
                <div key={s.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
                  <div style={{ flex: "2 1 220px" }}><b>{s.title}</b>
                    <div style={{ fontSize: 13, color: "var(--muted)" }}>{s.team} · {s.track} · {s.submitted_at ? `submitted ${fmtDate(s.submitted_at)}` : "not submitted"}</div></div>
                  <span className={`badge ${s.status === "SUBMITTED" ? "badge-ok" : "badge-warn"}`}>{s.status}</span>
                  {!s.is_visible && <span className="badge badge-muted">Hidden</span>}
                  <button className="btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => toggleVisibility(s.id, !s.is_visible)}>
                    {s.is_visible ? "Hide from gallery" : "Show in gallery"}
                  </button>
                </div>))}
            </div>
          )}
          {reviewTab === "people" && (
            <div>
              {!people.length && <p style={{ color: "var(--muted)" }}>Nobody has joined yet.</p>}
              {people.map((p: any) => (
                <div key={p.user_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)", flexWrap: "wrap" }}>
                  <b>{p.display_name}</b><span style={{ color: "var(--muted)" }}>{p.email}</span>
                  <span style={{ marginLeft: "auto", fontSize: 13, color: "var(--muted)" }}>
                    {p.team_name ? <>Team: <b>{p.team_name}</b></> : "No team yet"} · joined {fmtDate(p.joined_at)}
                  </span>
                </div>))}
            </div>
          )}
          {reviewTab === "team" && (
            <div>
              <p style={{ color: "var(--muted)" }}>Only these accounts can open this event's console, edit it, or moderate its submissions. Everyone else gets nothing — not even a preview of a draft.</p>
              <form onSubmit={addOrganizer} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "10px 0 4px" }}>
                <div style={{ flex: "1 1 240px" }}><label htmlFor="org-email">Add an organizer by email</label>
                  <input id="org-email" value={orgEmail} onChange={(e) => setOrgEmail(e.target.value)} placeholder="co-organizer@local.test" /></div>
                <button className="btn" type="submit">Add organizer</button>
              </form>
              <p className="form-note" style={{ marginTop: 0 }}>The account must already have the organizer role. Adding someone here grants access to this event only — it never grants a role.</p>
              {orgs.map((o: any) => (
                <div key={o.user_id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)", alignItems: "center", flexWrap: "wrap" }}>
                  <b>{o.display_name}</b><span style={{ color: "var(--muted)" }}>{o.email}</span>
                  <span className="badge badge-muted">{o.role}</span>
                  {o.is_owner && <span className="badge badge-ok">Creator</span>}
                  {!o.is_owner && <button className="link-btn" style={{ marginLeft: "auto" }} onClick={() => removeOrganizer(o.user_id)}>Remove</button>}
                </div>))}
              {!orgs.length && <p style={{ color: "var(--muted)" }}>No organizers listed.</p>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Organizer() {
  return <Suspense><Console /></Suspense>;
}
