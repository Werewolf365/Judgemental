"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, fetchMe } from "@/lib/api";
import { I } from "@/components/art";
import CustomAnswers from "@/components/CustomAnswers";
import JudgeGate from "@/components/JudgeGate";

function NewSubInner({ preselectTeam }: { preselectTeam: string }) {
  const [teams, setTeams] = useState<any[]>([]);
  const [tracks, setTracks] = useState<any[]>([]);
  const [f, setF] = useState({ team_id: "", event_id: "", track_id: "", title: "", summary: "", repo_url: "", description: "" });
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [noTeam, setNoTeam] = useState(false);
  const [isJudge, setIsJudge] = useState(false);
  const [eventsById, setEventsById] = useState<Record<string, any>>({});
  const [ownedByTeam, setOwnedByTeam] = useState<Record<string, any>>({});
  const router = useRouter();

  const isOpen = (eventId: string) => {
    const close = eventsById[eventId]?.submissions_close;
    if (!close) return true;
    return new Date(close).getTime() > Date.now();
  };

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      if (m.role === "JUDGE") { setIsJudge(true); return; }
      const t = await api("/teams");
      const list = t.teams || [];
      setTeams(list);
      if (!list.length) { setNoTeam(true); return; }
      try {
        const mine = await api("/submissions").catch(() => ({ projects: [] }));
        const owned: Record<string, any> = {};
        for (const p of mine.projects || []) owned[p.team_id] = p;
        setOwnedByTeam(owned);
        const ev = await api("/public/events");
        const map: Record<string, any> = {};
        for (const e of ev.events || []) map[e.id] = e;
        setEventsById(map);
        // Honor ?team= (Submit shortcut from the Events page) when it belongs
        // to the user; otherwise default to the first team in an open event
        // that does not already own a project (one submission per team).
        const firstOpen = list.find((x: any) => x.id === preselectTeam)
          || list.find((x: any) => {
            const c = map[x.event_id]?.submissions_close;
            return !owned[x.id] && (!c || new Date(c).getTime() > Date.now());
          }) || list[0];
        setF((s) => ({ ...s, team_id: firstOpen.id, event_id: firstOpen.event_id }));
        try { setTracks((await api(`/events/${firstOpen.event_id}/tracks`)).tracks?.filter((x: any) => x.is_active) || []); } catch {}
      } catch (e: any) { setMsg(e.message); }
    })().catch((e) => setMsg(e.message));
  }, [router, preselectTeam]);

  if (isJudge) return <JudgeGate />;
  if (noTeam) return (
    <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
      <h1>Join or create a team first</h1>
      <p>Projects belong to teams. Set one up from your workspace, then come back here.</p>
      <a href="/dashboard" className="btn">Go to workspace <I.arrow /></a>
    </div>
  );
  async function onTeam(id: string) {
    const t = teams.find((x) => x.id === id);
    setF({ ...f, team_id: t.id, event_id: t.event_id, track_id: "" });
    setCustom({});
    try { setTracks((await api(`/events/${t.event_id}/tracks`)).tracks?.filter((x: any) => x.is_active) || []); } catch {}
  }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!f.team_id || !f.track_id || !f.title.trim() || !f.summary.trim()) { setMsg("Team, track, title and summary are required."); return; }
    setBusy(true);
    try {
      const d = await api("/submissions", { method: "POST", body: JSON.stringify({ ...f, custom_data: custom }) });
      router.push(`/submissions/${d.project.id}/edit`);
    } catch (e: any) { setMsg(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Submissions</span><h1>New project</h1><p className="lead">Saved as a <b>draft</b> — only visible to your team until you submit.</p></div>
      <form className="card field" onSubmit={save} style={{ maxWidth: 720 }}>
        <label>Team</label>
        <select value={f.team_id} onChange={(e) => onTeam(e.target.value)}>
          <option value="">— pick a team —</option>
          {teams.map((t) => {
            const open = isOpen(t.event_id);
            const has = !!ownedByTeam[t.id];
            return <option key={t.id} value={t.id} disabled={!open || has}>{t.name}{has ? " — already has a project" : open ? "" : " — submissions closed"}</option>;
          })}
        </select>
        {ownedByTeam[f.team_id] && (
          <div className="deadline-bar" style={{ marginBottom: 14 }}><I.doc /> This team already has “{ownedByTeam[f.team_id].title}” — one submission per team. <a href={`/submissions/${ownedByTeam[f.team_id].id}/edit`}>Open it instead</a>.</div>
        )}
        {f.event_id && !isOpen(f.event_id) && (
          <div className="deadline-bar" style={{ marginBottom: 14 }}><I.clock /> This team's event stopped accepting submissions. Join an open event and create a team there instead.</div>
        )}
        <label>Track</label>
        <select value={f.track_id} onChange={(e) => setF({ ...f, track_id: e.target.value })}>
          <option value="">— pick a track —</option>
          {tracks.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        {!tracks.length && f.team_id && <p className="form-note">This event has no active tracks yet — ask the organizer to add some.</p>}
        <label>Title</label><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Quiet Hours" maxLength={120} />
        <label>Summary</label><input value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} placeholder="One line of what it does." maxLength={240} />
        <label>Description</label><textarea value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="What did you build, and how does it work?" />
        <label>Repository URL</label><input value={f.repo_url} onChange={(e) => setF({ ...f, repo_url: e.target.value })} placeholder="https://…" inputMode="url" />
        <CustomAnswers eventId={f.event_id} value={custom} onChange={setCustom} />
        {msg && <div className="form-error">{msg}</div>}
        <button className="btn" type="submit" disabled={busy || !!ownedByTeam[f.team_id]}>{busy ? "Saving…" : <>Save draft <I.arrow /></>}</button>
      </form>
    </div>
  );
}

function NewSubParams() {
  const sp = useSearchParams();
  return <NewSubInner preselectTeam={sp.get("team") || ""} />;
}

export default function NewSub() {
  return (
    <Suspense>
      <NewSubParams />
    </Suspense>
  );
}
