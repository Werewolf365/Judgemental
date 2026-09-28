"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe, fmtDate, type Me } from "@/lib/api";
import { I } from "@/components/art";

const ROLE_TONE: Record<string, string> = {
  ADMIN: "badge-ok",
  ORGANIZER: "badge-track",
  PARTICIPANT: "badge-muted",
  JUDGE: "badge-warn",
};

// Every role an admin may assign, in ascending order of privilege. Mirrors
// ASSIGNABLE_ROLES in backend/app/modules/admin/routes.py, which rejects
// anything outside this list.
const ASSIGNABLE = ["PARTICIPANT", "JUDGE", "ORGANIZER", "ADMIN"];

const ROLE_BLURB: Record<string, string> = {
  PARTICIPANT: "Competes in events. Can register, team up and submit.",
  JUDGE: "Scores projects. Does not register for events.",
  ORGANIZER: "Runs the events they are added to, and nothing else.",
  ADMIN: "Full platform access, including role management.",
};

function AccessDenied({ what }: { what: string }) {
  return (
    <div className="card empty">
      <h3>Admins only</h3>
      <p>{what} is restricted to accounts with the ADMIN role. Your account does not have it.</p>
    </div>
  );
}

function RolesTab({ me }: { me: Me }) {
  const [q, setQ] = useState("");
  const [users, setUsers] = useState<any[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState("");

  async function load(term = q) {
    try {
      const d = await api(`/admin/users?limit=100${term.trim() ? `&q=${encodeURIComponent(term.trim())}` : ""}`);
      setUsers(d.users || []);
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { load(""); }, []);

  async function changeRole(u: any, role: string) {
    if (!role || role === u.role) return;
    // Losing admin or organizer rights is worth one confirmation, since it
    // takes the account's access away immediately on their next request.
    const losing = u.role === "ADMIN" || u.role === "ORGANIZER" || u.role === "JUDGE";
    if (losing && !confirm(`Change ${u.email} from ${u.role} to ${role}? They lose ${u.role.toLowerCase()} access right away.`)) {
      await load();
      return;
    }
    setMsg(""); setBusy(u.id);
    try {
      const d = await api("/admin/users/role", { method: "POST", body: JSON.stringify({ email: u.email, role }) });
      setMsg(`${u.email} is now ${d.user.role}.`);
      await load();
    } catch (e: any) { setMsg(e.message); await load(); }
    finally { setBusy(""); }
  }

  return (
    <div>
      <p style={{ color: "var(--muted)" }}>
        Only an admin can change a role. Any account can be moved to any of the four roles — promoting a
        competitor to organizer or judge, and demoting one back. An organizer still sees nothing until they
        are added to a specific event, and nobody can change their own role or remove the last admin.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "12px 0" }}>
        <div style={{ flex: "1 1 260px" }}>
          <label htmlFor="user-search">Find an account</label>
          <input id="user-search" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="name or email" onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); load(); } }} />
        </div>
        <button className="btn" onClick={() => load()}>Search</button>
      </div>
      {msg && <p role="status">{msg}</p>}
      <div>
        {users.map((u) => {
          const isSelf = me?.id === u.id;
          const isBusy = busy === u.id;
          return (
            <div key={u.id} style={{ display: "flex", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line)", alignItems: "center", flexWrap: "wrap" }}>
              <b>{u.display_name}</b>
              <span style={{ color: "var(--muted)" }}>{u.email}</span>
              <span className={`badge ${ROLE_TONE[u.role] || "badge-muted"}`}>{u.role}</span>
              {isSelf && <span style={{ fontSize: 13, color: "var(--muted)" }}>that's you</span>}
              <span style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
                <label htmlFor={`role-${u.id}`} className="sr-only">Role for {u.email}</label>
                <select
                  id={`role-${u.id}`}
                  value={u.role}
                  disabled={isSelf || isBusy}
                  title={isSelf ? "You cannot change your own role" : `Change ${u.email}'s role`}
                  style={{ width: "auto", minWidth: 170, marginBottom: 0, padding: "7px 11px", fontSize: 14 }}
                  onChange={(e) => changeRole(u, e.target.value)}
                >
                  {ASSIGNABLE.map((r) => (
                    <option key={r} value={r}>{r === u.role ? `${r} — current` : `Make ${r.toLowerCase()}`}</option>
                  ))}
                </select>
              </span>
            </div>
          );
        })}
        {!users.length && <p style={{ color: "var(--muted)" }}>No accounts match.</p>}
      </div>
    </div>
  );
}

function AuditTab() {
  const [action, setAction] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<any>(null);
  const [offset, setOffset] = useState(0);
  const [msg, setMsg] = useState("");
  const LIMIT = 100;

  async function load(nextOffset = 0, act = action, term = q) {
    setMsg("");
    const qs = new URLSearchParams({ limit: String(LIMIT), offset: String(nextOffset) });
    if (act) qs.set("action", act);
    if (term.trim()) qs.set("q", term.trim());
    try {
      const d = await api(`/admin/audit?${qs}`);
      setData(d); setOffset(nextOffset);
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { load(0); }, []);

  const total = data?.total || 0;
  const from = total ? offset + 1 : 0;
  const to = Math.min(offset + LIMIT, total);

  return (
    <div>
      <p style={{ color: "var(--muted)" }}>
        Every sign-in, role change, organizer assignment, event edit and gallery moderation action, newest first.
        Passwords and session tokens are never recorded.
      </p>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", flexWrap: "wrap", margin: "12px 0" }}>
        <div style={{ flex: "1 1 200px" }}>
          <label htmlFor="audit-action">Action</label>
          <select id="audit-action" value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All actions</option>
            {(data?.actions || []).map((a: string) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
        <div style={{ flex: "1 1 200px" }}>
          <label htmlFor="audit-q">Search actor, action or target</label>
          <input id="audit-q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="organizer@local.test"
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); load(0); } }} />
        </div>
        <button className="btn" onClick={() => load(0)}>Apply</button>
      </div>
      {msg && <p role="alert">{msg}</p>}
      <div>
        {(data?.entries || []).map((e: any) => (
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
        {data && !data.entries?.length && <p style={{ color: "var(--muted)" }}>No entries match.</p>}
      </div>
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 12 }}>
        <button className="btn-ghost btn-sm" disabled={offset === 0} onClick={() => load(Math.max(0, offset - LIMIT))}>
          <I.back /> Newer
        </button>
        <span style={{ fontSize: 13, color: "var(--muted)" }}>{from}–{to} of {total}</span>
        <button className="btn-ghost btn-sm" disabled={to >= total} onClick={() => load(offset + LIMIT)}>
          Older <I.arrow />
        </button>
      </div>
    </div>
  );
}

export default function Admin() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<"roles" | "audit">("roles");
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setMe(m); setReady(true);
    })();
  }, [router]);

  if (!ready) return <div className="card"><div className="skel" style={{ height: 200 }} /></div>;

  // UX guard only. The API enforces this independently on every admin route.
  if (me?.role !== "ADMIN") {
    return (
      <div>
        <div className="page-head"><h1>Administration</h1></div>
        <AccessDenied what="Role management and the audit log" />
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <span className="eyebrow"><span className="dot" /> Admin</span>
        <h1>Administration</h1>
        <p className="lead">Grant roles and read the audit trail. Visible to admin accounts only.</p>
      </div>
      <div className="card field">
        <div className="tabs">
          <button className={tab === "roles" ? "on" : ""} onClick={() => setTab("roles")}>Roles</button>
          <button className={tab === "audit" ? "on" : ""} onClick={() => setTab("audit")}>Audit log</button>
        </div>
        {tab === "roles" ? <RolesTab me={me} /> : <AuditTab />}
      </div>
    </div>
  );
}
