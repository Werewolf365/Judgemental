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
  const [prof, setProf] = useState({ phone: "", age: "", degree: "", yearOfStudy: "", institution: "", dietaryRestrictions: "" });
  const [profMsg, setProfMsg] = useState("");
  const router = useRouter();

  useEffect(() => {
    (async () => {
      const m = await fetchMe();
      if (!m) { router.push("/login"); return; }
      setName(m.display_name);
      setAvatar((m as any).avatar_url || null);
      const p = (m as any).profile || {};
      setProf({
        phone: p.phone || "", age: p.age != null ? String(p.age) : "",
        degree: p.degree || "", yearOfStudy: p.year_of_study || "",
        institution: p.institution || "",
        dietaryRestrictions: p.dietary_restrictions || "",
      });
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

  function setP<K extends keyof typeof prof>(key: K, val: string) {
    setProf((p) => ({ ...p, [key]: val }));
  }

  async function saveProf(e: React.FormEvent) {
    e.preventDefault(); setProfMsg("");
    if (prof.phone.trim() && !/^\+?[\d\s\-()]{7,18}$/.test(prof.phone.trim())) { setProfMsg("Enter a valid phone number."); return; }
    if (prof.age.trim()) {
      const n = Number(prof.age);
      if (!Number.isInteger(n) || n < 13 || n > 120) { setProfMsg("Age must be between 13 and 120."); return; }
    }
    try {
      const d = await api("/auth/me", { method: "PATCH", body: JSON.stringify({ profile: {
        phone: prof.phone.trim(), age: prof.age.trim() === "" ? null : Number(prof.age),
        degree: prof.degree, year_of_study: prof.yearOfStudy,
        institution: prof.institution.trim(),
        dietary_restrictions: prof.dietaryRestrictions.trim(),
      } }) });
      const p = (d.user as any).profile || {};
      setProf({
        phone: p.phone || "", age: p.age != null ? String(p.age) : "",
        degree: p.degree || "", yearOfStudy: p.year_of_study || "",
        institution: p.institution || "",
        dietaryRestrictions: p.dietary_restrictions || "",
      });
      setProfMsg("Registration details saved — next event's form will prefill from these.");
    } catch (e: any) { setProfMsg(e.message); }
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
        <form className="card field" onSubmit={saveProf}>
          <h2>Registration details</h2>
          <p className="form-note">Save once, reuse everywhere — every event's registration form prefills from these, and you can still edit them per event.</p>
          <div className="reg-row">
            <div className="reg-col">
              <label>Phone number</label>
              <input type="tel" value={prof.phone} onChange={(e) => setP("phone", e.target.value)} placeholder="+91 98765 43210" />
            </div>
            <div className="reg-col" style={{ maxWidth: 130 }}>
              <label>Age</label>
              <input type="number" min={13} max={120} value={prof.age} onChange={(e) => setP("age", e.target.value)} placeholder="20" />
            </div>
          </div>
          <div className="reg-row">
            <div className="reg-col">
              <label>Degree / program</label>
              <select value={prof.degree} onChange={(e) => setP("degree", e.target.value)}>
                <option value="">Select…</option>
                {["B.Tech / B.E.", "B.Sc", "BCA", "M.Tech / M.E.", "M.Sc", "MCA", "MBA", "Ph.D.", "Diploma", "Other"].map((d) => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
            <div className="reg-col">
              <label>Year of study</label>
              <select value={prof.yearOfStudy} onChange={(e) => setP("yearOfStudy", e.target.value)}>
                <option value="">Select…</option>
                {["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year", "Graduated"].map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>
          </div>
          <label>Institution / college</label>
          <input value={prof.institution} onChange={(e) => setP("institution", e.target.value)} placeholder="Indian Institute of Technology Bombay" maxLength={300} />
          <label>Dietary restrictions</label>
          <input value={prof.dietaryRestrictions} onChange={(e) => setP("dietaryRestrictions", e.target.value)} placeholder="None, Vegetarian…" maxLength={500} />
          {profMsg && <p>{profMsg}</p>}
          <button className="btn" type="submit">Save details</button>
        </form>
      </div>
    </div>
  );
}
