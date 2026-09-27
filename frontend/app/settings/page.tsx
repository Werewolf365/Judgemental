"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, fetchMe } from "@/lib/api";

export default function Settings() {
  const [name, setName] = useState("");
  const [msg, setMsg] = useState("");
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setName(m.display_name);
    })();
  }, [router]);

  async function saveName(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!name.trim()) { setMsg("Display name can't be empty."); return; }
    try { await api("/auth/me", { method: "PATCH", body: JSON.stringify({ display_name: name.trim() }) }); setMsg("Profile updated."); }
    catch (e: any) { setMsg(e.message); }
  }

  async function savePw(e: React.FormEvent) {
    e.preventDefault(); setPwMsg("");
    if (next.length < 8) { setPwMsg("New password must be at least 8 characters."); return; }
    try {
      await api("/auth/password", { method: "POST", body: JSON.stringify({ current_password: cur, new_password: next }) });
      setCur(""); setNext(""); setPwMsg("Password changed.");
    } catch (e: any) { setPwMsg(e.message); }
  }

  return (
    <div>
      <div className="page-head"><span className="eyebrow"><span className="dot" /> Account</span><h1>Settings</h1></div>
      <div className="grid grid-2">
        <form className="card field" onSubmit={saveName}>
          <h2>Profile</h2>
          <label>Display name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} />
          {msg && <p>{msg}</p>}
          <button className="btn" type="submit">Save profile</button>
        </form>
        <form className="card field" onSubmit={savePw}>
          <h2>Password</h2>
          <label>Current password</label>
          <input type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" />
          <label>New password</label>
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
          {pwMsg && <p>{pwMsg}</p>}
          <button className="btn" type="submit">Change password</button>
        </form>
      </div>
    </div>
  );
}
