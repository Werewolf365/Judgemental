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
  const [avatar, setAvatar] = useState<string | null>(null);
  const [avatarMsg, setAvatarMsg] = useState("");
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setName(m.display_name);
      setAvatar((m as any).avatar_url || null);
    })();
  }, [router]);

  async function saveName(e: React.FormEvent) {
    e.preventDefault(); setMsg("");
    if (!name.trim()) { setMsg("Display name can't be empty."); return; }
    try { await api("/auth/me", { method: "PATCH", body: JSON.stringify({ display_name: name.trim() }) }); setMsg("Profile updated."); }
    catch (e: any) { setMsg(e.message); }
  }

  async function pickAvatar(e: React.ChangeEvent<HTMLInputElement>) {
    setAvatarMsg("");
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) { setAvatarMsg("Pick an image file."); return; }
    try {
      const bmp = await createImageBitmap(file);
      const S = 128;
      const scale = Math.min(1, S / Math.max(bmp.width, bmp.height));
      const w = Math.max(1, Math.round(bmp.width * scale));
      const h = Math.max(1, Math.round(bmp.height * scale));
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas unavailable");
      ctx.drawImage(bmp, 0, 0, w, h);
      const url = canvas.toDataURL("image/jpeg", 0.85);
      await api("/auth/me", { method: "PATCH", body: JSON.stringify({ avatar_url: url }) });
      setAvatar(url);
      setAvatarMsg("Profile picture updated.");
    } catch (err: any) { setAvatarMsg(err.message || "Could not read that image."); }
  }

  async function clearAvatar() {
    setAvatarMsg("");
    try {
      await api("/auth/me", { method: "PATCH", body: JSON.stringify({ avatar_url: "" }) });
      setAvatar(null);
      setAvatarMsg("Profile picture removed.");
    } catch (e: any) { setAvatarMsg(e.message); }
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
          <div style={{ display: "flex", gap: 14, alignItems: "center", marginBottom: 12 }}>
            {avatar
              ? <img src={avatar} alt="Profile picture" width={56} height={56} style={{ borderRadius: "50%", objectFit: "cover" }} />
              : <span className="avatar" style={{ width: 56, height: 56, fontSize: 20 }}>{(name || "?").slice(0, 2).toUpperCase()}</span>}
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <label className="btn-ghost btn-sm" style={{ cursor: "pointer" }}>Upload picture
                <input type="file" accept="image/*" onChange={pickAvatar} style={{ display: "none" }} /></label>
              {avatar && <button type="button" className="link-btn" onClick={clearAvatar}>Remove</button>}
            </div>
          </div>
          {avatarMsg && <p>{avatarMsg}</p>}
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
