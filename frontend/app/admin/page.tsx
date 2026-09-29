"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe, type Me } from "@/lib/api";
import Link from "next/link";

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

function KeysTab() {
  const [keys, setKeys] = useState<any[]>([]);
  const [allScopes, setAllScopes] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["events:read"]);
  const [days, setDays] = useState("");
  const [fresh, setFresh] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [copied, setCopied] = useState("");

  async function copy(text: string, what: string) {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select();
      document.execCommand("copy"); ta.remove();
    }
    setCopied(what);
    setTimeout(() => setCopied(""), 2000);
  }

  const SCOPE_EXAMPLES: Record<string, string> = {
    "events:read": "GET /events  —  list events you can manage",
    "events:write": "POST /events  —  create events, tracks, teams",
    "judging:read": "GET /events/{id}/results  —  read rankings",
    "judging:write": "POST /events/{id}/results/calculate  —  run calculations",
    "voting:read": "GET /events/{id}/voting/standings  —  live turnout",
    "voting:write": "POST /public/events/{slug}/ballot  —  cast votes",
    "transfer:read": "GET /events/{id}/export  —  download ZIP",
    "transfer:write": "POST /events/{id}/import  —  upload CSVs",
    "admin:read": "GET /admin/audit  —  read the audit trail",
    "admin:write": "POST /admin/users/role  —  grant roles",
  };
  function curlFor(path: string, token: string) {
    return `curl -H "Authorization: Bearer ${token}" http://localhost:8000${path}`;
  }

  async function load() {
    try {
      const d = await api("/admin/api-keys");
      setKeys(d.keys || []); setAllScopes(d.scopes || []);
    } catch (e: any) { setMsg(e.message); }
  }
  useEffect(() => { load(); }, []);

  function toggle(s: string) {
    setScopes((p) => p.includes(s) ? p.filter((x) => x !== s) : [...p, s]);
  }

  async function create(e: React.FormEvent) {
    e.preventDefault(); setMsg(""); setFresh(null);
    if (!email.includes("@")) { setMsg("Enter the owner's email address."); return; }
    if (!name.trim()) { setMsg("Give the key a name."); return; }
    if (!scopes.length) { setMsg("Pick at least one scope."); return; }
    try {
      const body: any = { email: email.trim(), name: name.trim(), scopes };
      if (days.trim() !== "") body.expires_in_days = Number(days);
      const d = await api("/admin/api-keys", { method: "POST", body: JSON.stringify(body) });
      setFresh(d); setEmail(""); setName(""); setDays("");
      await load();
    } catch (e: any) { setMsg(e.message); }
  }

  async function revoke(k: any) {
    if (!confirm(`Revoke key “${k.name}” (${k.user_email})? Calls using it start failing immediately.`)) return;
    try { await api(`/admin/api-keys/${k.id}`, { method: "DELETE" }); setMsg(`Key “${k.name}” revoked.`); await load(); }
    catch (e: any) { setMsg(e.message); }
  }

  return (
    <div>
      <p style={{ color: "var(--muted)" }}>
        Scoped bearer tokens for external integrations. A key acts as its owner — role checks and
        event scoping apply unchanged — and each area needs its scope (<span className="mono">area:read/write</span>).
        The token is shown <b>once</b> at creation; send it as <span className="mono">Authorization: Bearer …</span>.
      </p>
      {fresh?.token && (
        <div style={{ border: "1px solid var(--line)", borderRadius: 10, padding: 12, marginBottom: 12 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <b>Copy now — this never shows again.</b>
            <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
              <button type="button" className="btn-ghost btn-sm" onClick={() => copy(fresh.token, "token")}>
                {copied === "token" ? "Copied ✓" : "Copy token"}</button>
              <button type="button" className="link-btn" onClick={() => setFresh(null)}>Dismiss</button>
            </span>
          </div>
          <div className="mono" style={{ wordBreak: "break-all", marginTop: 6 }}>{fresh.token}</div>
          <p style={{ marginBottom: 6 }}>Key <b>{fresh.name}</b> for <b>{fresh.user_email}</b>
            {fresh.expires_at ? <> · expires {fresh.expires_at.slice(0, 10)}</> : " · no expiry"}.
            Send it as <span className="mono">Authorization: Bearer …</span></p>
          <div className="mono" style={{ fontSize: 12.5, background: "rgba(0,0,0,.04)", borderRadius: 8, padding: 10, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
            {curlFor("/auth/me", fresh.token)}
          </div>
          <button type="button" className="btn-ghost btn-sm" style={{ marginTop: 6 }}
            onClick={() => copy(curlFor("/auth/me", fresh.token), "whoami")}>
            {copied === "whoami" ? "Copied ✓" : "Copy whoami curl"}</button>
          {(fresh.scopes || []).filter((s: string) => SCOPE_EXAMPLES[s]).map((s: string) => {
            const [method, path] = SCOPE_EXAMPLES[s].startsWith("GET")
              ? ["GET", SCOPE_EXAMPLES[s].split(" — ")[0].replace("GET ", "")]
              : ["POST", SCOPE_EXAMPLES[s].split(" — ")[0].replace("POST ", "")];
            const cmd = method === "GET" ? curlFor(path, fresh.token)
              : `${curlFor(path, fresh.token)} -X POST -H "Content-Type: application/json" -d '{{}}'`;
            return (
              <div key={s} style={{ marginTop: 8 }}>
                <div style={{ fontSize: 13 }}><span className="mono">{s}</span> — {SCOPE_EXAMPLES[s].split(" — ")[1]}</div>
                <div className="mono" style={{ fontSize: 12.5, background: "rgba(0,0,0,.04)", borderRadius: 8, padding: 10, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {cmd}
                </div>
                <button type="button" className="btn-ghost btn-sm" style={{ marginTop: 6 }}
                  onClick={() => copy(cmd, s)}>
                  {copied === s ? "Copied ✓" : `Copy ${s} curl`}</button>
              </div>
            );
          })}
        </div>
      )}
      <form onSubmit={create} style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end", margin: "12px 0" }}>
        <div style={{ flex: "1 1 200px" }}>
          <label htmlFor="key-email">Owner email</label>
          <input id="key-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="organizer@local.test" />
        </div>
        <div style={{ flex: "1 1 160px" }}>
          <label htmlFor="key-name">Key name</label>
          <input id="key-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="dashboard sync" maxLength={100} />
        </div>
        <div style={{ flex: "0 1 120px" }}>
          <label htmlFor="key-days">Expires in (days)</label>
          <input id="key-days" type="number" min={1} max={3650} value={days} onChange={(e) => setDays(e.target.value)} placeholder="never" />
        </div>
        <button className="btn" type="submit">Create key</button>
      </form>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        {allScopes.map((s) => (
          <label key={s} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13.5, fontWeight: 400 }}>
            <input type="checkbox" checked={scopes.includes(s)} onChange={() => toggle(s)} style={{ width: "auto", margin: 0 }} />
            <span className="mono">{s}</span>
          </label>
        ))}
      </div>
      {msg && <p role="status">{msg}</p>}
      <div>
        {keys.map((k) => (
          <div key={k.id} style={{ display: "flex", gap: 10, padding: "9px 0", borderTop: "1px solid var(--line)", alignItems: "center", flexWrap: "wrap" }}>
            <b>{k.name}</b>
            <span style={{ color: "var(--muted)" }}>{k.user_email}</span>
            {k.revoked_at
              ? <span className="badge badge-muted">revoked</span>
              : <span className="badge badge-ok">active</span>}
            <span className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>{(k.scopes || []).join(" · ")}</span>
            <span style={{ marginLeft: "auto", fontSize: 12.5, color: "var(--muted)" }}>
              {k.expires_at ? `expires ${k.expires_at.slice(0, 10)}` : "no expiry"} · last used {k.last_used_at ? k.last_used_at.slice(0, 16).replace("T", " ") : "never"}
            </span>
            {!k.revoked_at && <button className="link-btn" onClick={() => revoke(k)}>Revoke</button>}
          </div>
        ))}
        {!keys.length && <p style={{ color: "var(--muted)" }}>No API keys yet.</p>}
      </div>
    </div>
  );
}

export default function Admin() {
  const [me, setMe] = useState<Me>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<"roles" | "keys">("roles");
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
        <AccessDenied what="Role management" />
      </div>
    );
  }

  return (
    <div>
      <div className="page-head">
        <span className="eyebrow"><span className="dot" /> Admin</span>
        <h1>Administration</h1>
        <p className="lead">Grant roles and manage API keys. The audit trail now lives under <Link href="/security">Security</Link>, where it is filterable and searchable per event or platform-wide.</p>
      </div>
      <div className="card field">
        <div className="tabs">
          <button className={tab === "roles" ? "on" : ""} onClick={() => setTab("roles")}>Roles</button>
          <button className={tab === "keys" ? "on" : ""} onClick={() => setTab("keys")}>API keys</button>
        </div>
        {tab === "roles" ? <RolesTab me={me} /> : <KeysTab />}
      </div>
    </div>
  );
}
