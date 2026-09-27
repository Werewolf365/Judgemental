"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { I } from "@/components/art";

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const r = useRouter();

  async function go(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    if (!email.includes("@")) { setErr("Enter a valid email address."); return; }
    if (password.length < 8) { setErr("Password must be at least 8 characters."); return; }
    setBusy(true);
    try {
      if (mode === "login") await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      else await api("/auth/register", { method: "POST", body: JSON.stringify({ email, password, display_name: name }) });
      r.push("/dashboard");
    } catch (e: any) { setErr(e.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="card auth-split" style={{ maxWidth: 880, margin: "30px auto" }}>
      <div className="auth-brand">
        <svg width="120" height="70" viewBox="0 0 120 70" aria-hidden>
          <ellipse cx="30" cy="18" rx="22" ry="8" fill="#fff" opacity=".7" />
          <ellipse cx="86" cy="12" rx="26" ry="9" fill="#fff" opacity=".55" />
          <path d="M0 52 Q 30 40 60 48 T 120 50 V70 H0 Z" fill="#ffffff" opacity=".35" />
          <circle cx="96" cy="34" r="10" fill="#fff7d6" opacity=".9" />
        </svg>
        <h2>{mode === "login" ? "Welcome back." : "Create your account."}</h2>
        <p>{mode === "login" ? "Log in to manage your team, drafts and submissions." : "One account for every hackathon. Join events, form teams, submit projects."}</p>
        <div style={{ marginTop: 22, fontSize: 13.5, color: "#d7efe9" }}>
          Local demo logins — password <span className="mono" style={{ background: "rgba(255,255,255,.18)", color: "#fff", border: 0 }}>Local123!</span><br />
          organizer@local.test · participant@local.test
        </div>
      </div>
      <form className="auth-form field" onSubmit={go}>
        <h1 style={{ fontSize: 26 }}>{mode === "login" ? "Log in" : "Create account"}</h1>
        {mode === "register" && (<><label htmlFor="name">Display name</label><input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" autoComplete="name" /></>)}
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@team.org" autoComplete="email" />
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Minimum 8 characters" autoComplete={mode === "login" ? "current-password" : "new-password"} />
        {err && <div className="form-error" role="alert">{err}</div>}
        <button className="btn" type="submit" disabled={busy} style={{ width: "100%" }}>{busy ? "Please wait…" : mode === "login" ? <>Log in <I.arrow /></> : <>Create account <I.arrow /></>}</button>
        <p className="form-note" style={{ marginTop: 12 }}>
          {mode === "login" ? <>New here? <Link href="/register">Create an account</Link></> : <>Have an account? <Link href="/login">Log in</Link></>}
        </p>
      </form>
    </div>
  );
}
