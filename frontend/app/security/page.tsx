"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe, fmtDate, type Me } from "@/lib/api";
import { I } from "@/components/art";

type Tab = "audit" | "flags" | "blocks";

const KIND_TONE: Record<string, string> = {
  rate_limit: "badge-warn",
  own_team_vote: "badge-track",
  shared_device: "badge-warn",
  comment_flood: "badge-muted",
};
const KIND_WORD: Record<string, string> = {
  rate_limit: "Rate-limit hit",
  own_team_vote: "Own-team vote attempt",
  shared_device: "Shared device",
  comment_flood: "Comment flood",
};

function AuditEntries({ entries }: { entries: any[] }) {
  return (
    <div>
      {entries.map((e: any) => (
        <div key={e.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="badge badge-track">{e.action}</span>
            <b>{e.actor_email || "anonymous"}</b>
            <span style={{ color: "var(--muted)", fontSize: 13 }}>
              {fmtDate(e.created_at)}{e.ip ? ` · ${e.ip}` : ""}
            </span>
            {e.target_id && <span style={{ color: "var(--muted)", fontSize: 13 }}>→ {e.target_type}:{e.target_id}</span>}
          </div>
          {e.detail && Object.keys(e.detail).length > 0 && (
            <div className="mono" style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 3, wordBreak: "break-word" }}>
              {JSON.stringify(e.detail)}
            </div>
          )}
        </div>
      ))}
      {!entries.length && <p style={{ color: "var(--muted)" }}>No entries match.</p>}
    </div>
  );
}

export default function Security() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  const [events, setEvents] = useState<any[]>([]);
  const [eventId, setEventId] = useState("");
  const [tab, setTab] = useState<Tab>("audit");
  const [overview, setOverview] = useState<any>(null);
  const [flags, setFlags] = useState<any[]>([]);
  const [flagFilter, setFlagFilter] = useState("open");
  const [blocks, setBlocks] = useState<any[]>([]);
  const [showRevoked, setShowRevoked] = useState(false);
  const [btType, setBtType] = useState("user");
  const [btTarget, setBtTarget] = useState("");
  const [btReason, setBtReason] = useState("");
  const [auditAction, setAuditAction] = useState("");
  const [auditQ, setAuditQ] = useState("");
  const [audit, setAudit] = useState<any>(null);
  const [auditOffset, setAuditOffset] = useState(0);
  const [subjects, setSubjects] = useState<Record<string, any[]>>({});
  const [msg, setMsg] = useState("");
  const router = useRouter();
  const isAdmin = me?.role === "ADMIN";
  const AUDIT_LIMIT = 100;
  const evSlug = events.find((x: any) => x.id === eventId)?.slug || eventId;

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setMe(m); setReady(true);
      if (m.role !== "ORGANIZER" && m.role !== "ADMIN") return;
      try {
        const list = await api("/events");
        const evs = list.events || [];
        setEvents(evs);
        const want = new URLSearchParams(window.location.search).get("event");
        if (want && evs.some((x: any) => x.id === want || x.slug === want)) {
          const hit = evs.find((x: any) => x.id === want || x.slug === want);
          setEventId(hit.id);
        } else if (evs[0]) setEventId(evs[0].id);
      } catch (e: any) { setMsg(e.message); }
    })();
  }, [router]);

  async function loadAll(id: string, flagStatus = flagFilter, includeRev = showRevoked) {
    if (!id) return;
    setMsg("");
    try {
      const [o, f, b] = await Promise.all([
        api(`/events/${id}/security/overview`).catch(() => null),
        api(`/events/${id}/security/flags${flagStatus ? `?status=${flagStatus}` : ""}`).catch(() => ({ flags: [] })),
        api(`/events/${id}/security/blocks${includeRev ? "?include_revoked=true" : ""}`).catch(() => ({ blocks: [] })),
      ]);
      setOverview(o);
      setFlags(f.flags || []);
      setBlocks(b.blocks || []);
    } catch (e: any) { setMsg(e.message); }
    await loadAudit(id, 0);
  }
  useEffect(() => {
    if (!eventId) return;
    setAuditAction(""); setAuditQ("");
    if (eventId === "__all__") {
      setOverview(null); setFlags([]); setBlocks([]);
      loadAudit("__all__", 0, "", "");
      return;
    }
    loadAll(eventId);
  }, [eventId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function loadAudit(id: string, offset: number, act = auditAction, term = auditQ) {
    if (!id) return;
    setMsg("");
    try {
      // Admins read the platform-wide trail filtered to this event (or all
      // events when cleared); organizers read the event-scoped trail.
      const qs = new URLSearchParams({ limit: String(AUDIT_LIMIT), offset: String(offset) });
      if (isAdmin) {
        if (id !== "__all__") qs.set("event_id", id);
        if (act) qs.set("action", act);
        if (term.trim()) qs.set("q", term.trim());
        setAudit(await api(`/admin/audit?${qs}`));
      } else {
        if (act) qs.set("action", act);
        if (term.trim()) qs.set("q", term.trim());
        const d = await api(`/events/${id}/audit?${qs}`);
        setAudit({ entries: d.entries || [], total: (d.entries || []).length, actions: d.actions || [] });
      }
      setAuditOffset(offset);
    } catch (e: any) { setMsg(e.message); }
  }

  async function dismissFlag(fid: string) {
    setMsg("");
    try {
      await api(`/events/${eventId}/security/flags/${fid}/dismiss`, { method: "POST", body: "{}" });
      setMsg("Flag dismissed — a repeat offence reopens it.");
      await loadAll(eventId);
    } catch (e: any) { setMsg(e.message); }
  }

  async function createBlock(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!btTarget.trim()) { setMsg("Enter a user id, email, or IP to block."); return; }
    try {
      const d = await api(`/events/${eventId}/security/blocks`, { method: "POST",
        body: JSON.stringify({ target_type: btType, target: btTarget.trim(), reason: btReason.trim() || null }) });
      setBtTarget(""); setBtReason("");
      setMsg(`Blocked ${d.block.target_type} ${d.block.target} — open flags on it are marked blocked.`);
      await loadAll(eventId);
    } catch (e: any) { setMsg(e.message); }
  }

  async function revokeBlock(bid: string) {
    if (!confirm("Lift this block? The writer can vote and comment again right away.")) return;
    setMsg("");
    try {
      await api(`/events/${eventId}/security/blocks/${bid}`, { method: "DELETE" });
      setMsg("Block lifted.");
      await loadAll(eventId);
    } catch (e: any) { setMsg(e.message); }
  }

  function prefillBlock(type: string, target: string) {
    setBtType(type); setBtTarget(target);
    setTab("blocks");
  }

  async function loadSubjects(fid: string) {
    if (subjects[fid]) { setSubjects((s) => { const n = { ...s }; delete n[fid]; return n; }); return; }
    try {
      const d = await api(`/events/${eventId}/security/flags/${fid}/subjects`);
      setSubjects((s) => ({ ...s, [fid]: d.subjects || [] }));
    } catch (e: any) { setMsg(e.message); }
  }

  const BLOCK_WORD: Record<string, string> = { user: "Block user", ip: "Block IP", voter: "Block ballot key" };

  if (!ready) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;
  if (me?.role !== "ORGANIZER" && me?.role !== "ADMIN") {
    return (
      <div>
        <div className="page-head"><h1>Security</h1></div>
        <div className="card empty"><h3>Organizers only</h3>
          <p>Abuse flags, blocks and audit trails are restricted to accounts that run events.</p></div>
      </div>
    );
  }

  const auditTotal = audit?.total ?? (audit?.entries || []).length;
  const auditFrom = auditTotal ? auditOffset + 1 : 0;
  const auditTo = Math.min(auditOffset + AUDIT_LIMIT, auditTotal);

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Safety</span>
        <h1>Security</h1>
        <p className="lead">Who tripped the alarms, who is blocked, and the full audit trail — per event, no database client needed.</p></div>
      {msg && <div className="card"><p role="status">{msg}</p></div>}
      <div className="card field">
        <label>Event</label>
        <select value={eventId} onChange={(e) => setEventId(e.target.value)}>
          {isAdmin && <option value="__all__">All events (audit only)</option>}
          {events.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
        {overview && eventId !== "__all__" && (
          <p style={{ color: "var(--muted)" }} role="status">
            <b style={{ color: "var(--ink)" }}>{overview.open_flag_total}</b> open flag{overview.open_flag_total === 1 ? "" : "s"}
            {Object.entries(overview.open_flags || {}).map(([k, n]) => ` · ${KIND_WORD[k] || k}: ${n}`).join("")}
            {" · "}<b style={{ color: "var(--ink)" }}>{overview.active_blocks}</b> active block{overview.active_blocks === 1 ? "" : "s"}
            {" · "}{overview.refusals} refused writes on record
          </p>
        )}
        {eventId !== "__all__" ? (
          <>
            <div className="tabs">
              <button className={tab === "audit" ? "on" : ""} onClick={() => setTab("audit")}>Audit log</button>
              <button className={tab === "flags" ? "on" : ""} onClick={() => setTab("flags")}>Flags ({overview?.open_flag_total ?? "…"})</button>
              <button className={tab === "blocks" ? "on" : ""} onClick={() => setTab("blocks")}>Blocks ({overview?.active_blocks ?? "…"})</button>
              <button className="btn-ghost btn-sm" style={{ marginLeft: "auto", alignSelf: "center" }} onClick={() => eventId && loadAll(eventId)}>Refresh</button>
            </div>
            {tab === "flags" && (
              <div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
                  <span style={{ fontSize: 13.5, color: "var(--muted)" }}>A repeat offence reopens a dismissed flag instead of duplicating it.</span>
                  <select value={flagFilter} onChange={(e) => { setFlagFilter(e.target.value); if (eventId) loadAll(eventId, e.target.value, showRevoked); }}
                    style={{ width: "auto", marginLeft: "auto", marginBottom: 0 }}>
                    <option value="open">Open only</option>
                    <option value="">All statuses</option>
                    <option value="blocked">Blocked</option>
                    <option value="dismissed">Dismissed</option>
                  </select>
                </div>
                {!flags.length && <p style={{ color: "var(--muted)" }}>No flags — nothing tripped the alarms on this event.</p>}
                {flags.map((f: any) => (
                  <div key={f.id} style={{ padding: "10px 0", borderTop: "1px solid var(--line)" }}>
                    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <span className={`badge ${KIND_TONE[f.kind] || "badge-muted"}`}>{KIND_WORD[f.kind] || f.kind}</span>
                      <span className="mono">{f.subject_type}:{f.subject}</span>
                      <span className={`badge ${f.status === "open" ? "badge-warn" : "badge-muted"}`}>{f.status}</span>
                      <span style={{ marginLeft: "auto", color: "var(--muted)", fontSize: 13 }}>{fmtDate(f.updated_at)}</span>
                    </div>
                    {f.detail && Object.keys(f.detail).length > 0 && (
                      <div className="mono" style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 3, wordBreak: "break-word" }}>
                        {JSON.stringify(f.detail)}
                      </div>
                    )}
                    {f.status === "open" && (
                      <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap", alignItems: "center" }}>
                        <a className="btn-ghost btn-sm" href={`/events/${evSlug}`}>View event</a>
                        {f.subject_type === "fingerprint" ? (
                          <button className="btn-ghost btn-sm" onClick={() => loadSubjects(f.id)}>
                            {subjects[f.id] ? "Hide writers" : "Show writers"}</button>
                        ) : (
                          <button className="btn-ghost btn-sm" onClick={() =>
                            prefillBlock(f.subject_type === "ip" ? "ip" : f.subject_type === "voter" ? "voter" : "user", f.subject)}>
                            {BLOCK_WORD[f.subject_type] || "Block this subject"}</button>
                        )}
                        <button className="link-btn" onClick={() => dismissFlag(f.id)}>Dismiss</button>
                      </div>
                    )}
                    {subjects[f.id] && (
                      <div style={{ marginTop: 6 }}>
                        {subjects[f.id].map((s: any) => (
                          <div key={s.type + s.target} style={{ display: "flex", gap: 8, alignItems: "center", padding: "4px 0", fontSize: 13.5, flexWrap: "wrap" }}>
                            <span className="mono">{s.target}</span>
                            {s.ballots != null && <span style={{ color: "var(--muted)" }}>{s.ballots} ballot{s.ballots === 1 ? "" : "s"}</span>}
                            <button className="btn-ghost btn-sm" onClick={() => prefillBlock(s.type, s.target)}>
                              {BLOCK_WORD[s.type] || "Block"}</button>
                          </div>
                        ))}
                        {!subjects[f.id].length && <p style={{ color: "var(--muted)", fontSize: 13.5 }}>No ballots left under this fingerprint.</p>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {tab === "blocks" && (
              <div>
                <p style={{ color: "var(--muted)" }}>Blocks stop ballot casts and comment posts from that user, ballot key, or IP on this event. Email targets resolve to the account at write time.</p>
                <form onSubmit={createBlock} style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "10px 0" }}>
                  <div style={{ flex: "0 1 130px" }}><label htmlFor="block-type">Type</label>
                    <select id="block-type" value={btType} onChange={(e) => setBtType(e.target.value)}>
                      <option value="user">User</option>
                      <option value="voter">Ballot key</option>
                      <option value="ip">IP</option>
                    </select></div>
                  <div style={{ flex: "2 1 220px" }}><label htmlFor="block-target">User id, email, ballot key, or IP</label>
                    <input id="block-target" value={btTarget} onChange={(e) => setBtTarget(e.target.value)} placeholder={btType === "ip" ? "203.0.113.7" : "user id or email"} /></div>
                  <div style={{ flex: "2 1 220px" }}><label htmlFor="block-reason">Reason (optional)</label>
                    <input id="block-reason" value={btReason} onChange={(e) => setBtReason(e.target.value)} placeholder="Ballot stuffing" maxLength={500} /></div>
                  <button className="btn" type="submit">Block</button>
                </form>
                <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14 }}>
                  <input type="checkbox" checked={showRevoked} onChange={(e) => { setShowRevoked(e.target.checked); if (eventId) loadAll(eventId, flagFilter, e.target.checked); }} style={{ width: "auto", margin: 0 }} /> Show lifted blocks</label>
                {!blocks.length && <p style={{ color: "var(--muted)" }}>No blocks on this event.</p>}
                {blocks.map((b: any) => (
                  <div key={b.id} style={{ display: "flex", gap: 10, padding: "8px 0", borderTop: "1px solid var(--line)", alignItems: "center", flexWrap: "wrap" }}>
                    <span className={`badge ${b.revoked_at ? "badge-muted" : "badge-warn"}`}>{b.target_type}</span>
                    <b className="mono">{b.target}</b>
                    {b.reason && <span style={{ color: "var(--muted)", fontSize: 13.5 }}>{b.reason}</span>}
                    <span style={{ marginLeft: "auto", color: "var(--muted)", fontSize: 13 }}>{fmtDate(b.created_at)}</span>
                    {!b.revoked_at
                      ? <button className="link-btn" onClick={() => revokeBlock(b.id)}>Lift block</button>
                      : <span className="badge badge-muted">lifted {fmtDate(b.revoked_at)}</span>}
                  </div>
                ))}
              </div>
            )}
            {tab === "audit" && (
              <div>
                <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "10px 0" }}>
                  <div style={{ flex: "1 1 180px" }}><label htmlFor="sec-action">Action</label>
                    <select id="sec-action" value={auditAction} onChange={(e) => setAuditAction(e.target.value)}>
                      <option value="">All actions</option>
                      {(audit?.actions || []).map((a: string) => <option key={a} value={a}>{a}</option>)}
                    </select></div>
                  <div style={{ flex: "2 1 240px" }}><label htmlFor="sec-q">Search actor or target</label>
                    <input id="sec-q" value={auditQ} onChange={(e) => setAuditQ(e.target.value)} placeholder="email, IP, or id"
                      onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); loadAudit(eventId, 0); } }} /></div>
                  <button className="btn" onClick={() => loadAudit(eventId, 0)}>Apply</button>
                </div>
                <AuditEntries entries={audit?.entries || []} />
                {isAdmin && (
                  <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
                    <button className="btn-ghost btn-sm" disabled={auditOffset === 0} onClick={() => loadAudit(eventId, Math.max(0, auditOffset - AUDIT_LIMIT))}>
                      <I.back /> Newer</button>
                    <span style={{ fontSize: 13, color: "var(--muted)" }}>{auditFrom}–{auditTo} of {auditTotal}</span>
                    <button className="btn-ghost btn-sm" disabled={auditTo >= auditTotal} onClick={() => loadAudit(eventId, auditOffset + AUDIT_LIMIT)}>
                      Older <I.arrow /></button>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <div>
            <p style={{ color: "var(--muted)" }}>Platform-wide audit trail. Pick an event above to scope it, or search across everything.</p>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "10px 0" }}>
              <div style={{ flex: "1 1 180px" }}><label htmlFor="sec-action-all">Action</label>
                <input id="sec-action-all" value={auditAction} onChange={(e) => setAuditAction(e.target.value)} placeholder="vote.rate_limited" /></div>
              <div style={{ flex: "2 1 240px" }}><label htmlFor="sec-q-all">Search actor, action or target</label>
                <input id="sec-q-all" value={auditQ} onChange={(e) => setAuditQ(e.target.value)} placeholder="email or IP"
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); loadAudit("__all__", 0); } }} /></div>
              <button className="btn" onClick={() => loadAudit("__all__", 0)}>Apply</button>
            </div>
            <AuditEntries entries={audit?.entries || []} />
            <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
              <button className="btn-ghost btn-sm" disabled={auditOffset === 0} onClick={() => loadAudit("__all__", Math.max(0, auditOffset - AUDIT_LIMIT))}>
                <I.back /> Newer</button>
              <span style={{ fontSize: 13, color: "var(--muted)" }}>{auditFrom}–{auditTo} of {auditTotal}</span>
              <button className="btn-ghost btn-sm" disabled={auditTo >= auditTotal} onClick={() => loadAudit("__all__", auditOffset + AUDIT_LIMIT)}>
                Older <I.arrow /></button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
