"use client";
import { useEffect, useState } from "react";
import { api, fetchMe, initials } from "@/lib/api";

/** Project discussion thread. Read access follows the event's
 *  comments_visibility (public vs team-only); posting needs a login;
 *  organizers see a hide toggle per comment. Loads once — no polling. */
export default function Comments({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState("");
  const [loaded, setLoaded] = useState(false);

  async function load() {
    try {
      const me = await fetchMe();
      setRole(me?.role || "");
      setItems((await api(`/public/projects/${projectId}/comments`)).comments || []);
    } catch (e: any) { setMsg(e.message); }
    finally { setLoaded(true); }
  }
  useEffect(() => { load(); }, [projectId]);

  async function post(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!body.trim()) return;
    setBusy(true);
    try {
      await api(`/public/projects/${projectId}/comments`,
        { method: "POST", body: JSON.stringify({ body: body.trim() }) });
      setBody("");
      await load();
    } catch (err: any) { setMsg(err.message); }
    finally { setBusy(false); }
  }

  async function hide(id: string, hidden: boolean) {
    try {
      await api(`/comments/${id}`, { method: "PATCH", body: JSON.stringify({ is_hidden: hidden }) });
      await load();
    } catch (e: any) { setMsg(e.message); }
  }

  const staff = role === "ORGANIZER" || role === "ADMIN";
  if (!loaded) return <div className="card"><div className="skel" style={{ height: 80 }} /></div>;
  return (
    <div className="card field">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <h2 style={{ margin: 0 }}>Discussion</h2>
        <span className="badge badge-muted">{items.length} comment{items.length === 1 ? "" : "s"}</span>
      </div>
      {!items.length
        ? <div className="empty" style={{ padding: "20px 12px" }}>
            <h3>No comments yet</h3>
            <p>{role ? "Start the conversation below." : "Log in to start the conversation."}</p>
          </div>
        : <div style={{ marginTop: 6 }}>
            {items.map((c) => (
              <div key={c.id} style={{ display: "flex", gap: 12, padding: "12px 0", borderTop: "1px solid var(--line)" }}>
                {c.author_avatar
                  ? <img src={c.author_avatar} alt="" width={28} height={28} style={{ borderRadius: "50%", objectFit: "cover", flexShrink: 0 }} />
                  : <span className="avatar" aria-hidden>{initials(c.author || "?")}</span>}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                    <b>{c.author}</b>
                    <span style={{ color: "var(--muted)", fontSize: 12.5 }}>
                      {c.created_at ? new Date(c.created_at).toLocaleString() : ""}</span>
                    {c.is_hidden && <span className="badge badge-muted">Hidden</span>}
                    {staff && !c.is_hidden && (
                      <button className="link-btn" style={{ marginLeft: "auto", padding: "2px 6px" }}
                        onClick={() => hide(c.id, true)}>Hide</button>)}
                    {staff && c.is_hidden && (
                      <button className="link-btn" style={{ marginLeft: "auto", padding: "2px 6px" }}
                        onClick={() => hide(c.id, false)}>Show</button>)}
                  </div>
                  <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{c.body}</p>
                </div>
              </div>
            ))}
          </div>}
      <form onSubmit={post} style={{ marginTop: 14 }}>
        <label htmlFor={`comment-${projectId}`}>Add a comment</label>
        <textarea id={`comment-${projectId}`} rows={3} value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={role ? "Be kind and specific…" : "Log in to join the discussion…"}
          disabled={!role || busy} maxLength={2000} style={{ resize: "vertical" }} />
        {msg && <p>{msg}</p>}
        <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 4 }}>
          <button className="btn btn-sm" type="submit" disabled={!role || busy || !body.trim()}>Post comment</button>
          {!role && <span className="form-note">You need an account to comment.</span>}
          {role && <span className="form-note">{2000 - body.length} characters left</span>}
        </div>
      </form>
    </div>
  );
}
