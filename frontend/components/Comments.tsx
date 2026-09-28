"use client";
import { useEffect, useState } from "react";
import { api, fetchMe } from "@/lib/api";

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
    <div className="card">
      <h2>Discussion ({items.length})</h2>
      {!items.length && <p style={{ color: "var(--muted)" }}>No comments yet — start the conversation.</p>}
      {items.map((c) => (
        <div key={c.id} style={{ padding: "8px 0", borderTop: "1px solid var(--line)" }}>
          <b>{c.author}</b> <span style={{ color: "var(--muted)", fontSize: 13 }}>
            {c.created_at ? new Date(c.created_at).toLocaleString() : ""}</span>
          {c.is_hidden && <span className="badge badge-muted" style={{ marginLeft: 8 }}>Hidden</span>}
          <p style={{ margin: "4px 0 0", whiteSpace: "pre-wrap" }}>{c.body}</p>
          {staff && !c.is_hidden && <button className="link-btn" onClick={() => hide(c.id, true)}>Hide</button>}
          {staff && c.is_hidden && <button className="link-btn" onClick={() => hide(c.id, false)}>Show</button>}
        </div>
      ))}
      <form onSubmit={post} style={{ marginTop: 10 }}>
        <label htmlFor={`comment-${projectId}`}>Add a comment</label>
        <textarea id={`comment-${projectId}`} value={body} onChange={(e) => setBody(e.target.value)}
          placeholder={role ? "Be kind and specific…" : "Log in to join the discussion…"}
          disabled={!role || busy} maxLength={2000} />
        {msg && <p>{msg}</p>}
        <button className="btn btn-sm" type="submit" disabled={!role || busy || !body.trim()}>Post comment</button>
      </form>
    </div>
  );
}
