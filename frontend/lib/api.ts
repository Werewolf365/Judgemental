export type Me = { id: string; email: string; display_name: string; role: string } | null;

export async function api(path: string, opts: RequestInit = {}) {
  const res = await fetch(path.startsWith("http") ? path : `/api${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await res.text();
  let data: any = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    if (Array.isArray(data?.detail)) {
      msg = data.detail.map((e: any) => `${e.loc?.slice(-1)?.[0] || 'Field'}: ${e.msg}`).join(", ");
    } else if (data?.detail?.message) {
      msg = data.detail.message;
    } else if (data?.detail && typeof data.detail === "string") {
      msg = data.detail;
    } else if (data?.message) {
      msg = data.message;
    }
    throw new Error(msg);
  }
  return data;
}

export async function fetchMe(): Promise<Me> {
  try {
    const d = await api("/auth/me");
    return d.user as Me;
  } catch {
    return null;
  }
}

export async function logout() {
  try { await api("/auth/logout", { method: "POST", body: "{}" }); } catch {}
  window.location.href = "/";
}

export const fmtDate = (s?: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—";

/** Deterministic gradient thumb from any id string (no external images). */
export function thumbStyle(id: string): React.CSSProperties {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 360;
  const h2 = (h + 60) % 360;
  return {
    background: `linear-gradient(120deg, hsl(${h} 65% 42%) 0%, hsl(${h2} 70% 48%) 55%, hsl(${(h2 + 40) % 360} 75% 62%) 100%)`,
  };
}

export function initials(name: string) {
  return (name || "?").split(/[\s@._-]+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
}

/** Live countdown parts to a deadline ISO string. */
export function useCountdown(deadline?: string | null) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => {
    if (!deadline) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [deadline]);
  if (!deadline) return null;
  const ms = new Date(deadline).getTime() - now;
  const past = ms <= 0;
  const abs = Math.abs(ms);
  const d = Math.floor(abs / 864e5);
  const h = Math.floor((abs % 864e5) / 36e5);
  const m = Math.floor((abs % 36e5) / 6e4);
  const s = Math.floor((abs % 6e4) / 1e3);
  return { past, d, h, m, s };
}

import React from "react";
