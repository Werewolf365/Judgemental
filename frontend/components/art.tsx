"use client";
import React from "react";

/* Hand-drawn-feeling local SVG icon set (no emoji, no CDN). */
function base(props: React.SVGProps<SVGSVGElement>) {
  return {
    width: 15, height: 15, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const, className: "icon", "aria-hidden": true, ...props,
  };
}
export const I = {
  arrow: (p: any) => <svg {...base(p)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>,
  back: (p: any) => <svg {...base(p)}><path d="M19 12H5M11 18l-6-6 6-6" /></svg>,
  clock: (p: any) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 3" /></svg>,
  pin: (p: any) => <svg {...base(p)}><path d="M12 21s-7-5.5-7-11a7 7 0 0 1 14 0c0 5.5-7 11-7 11z" /><circle cx="12" cy="10" r="2.6" /></svg>,
  team: (p: any) => <svg {...base(p)}><circle cx="9" cy="8" r="3.4" /><path d="M3.5 20c.6-3.4 2.8-5 5.5-5s4.9 1.6 5.5 5" /><circle cx="17" cy="9" r="2.6" /><path d="M15.5 14.6c2.9.1 4.5 1.7 5 4.4" /></svg>,
  doc: (p: any) => <svg {...base(p)}><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4M9 12h6M9 16h6" /></svg>,
  globe: (p: any) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.5 3 14 0 18M12 3c-3 3.5-3 14 0 18" /></svg>,
  play: (p: any) => <svg {...base(p)}><circle cx="12" cy="12" r="9" /><path d="M10 8.5l5 3.5-5 3.5z" /></svg>,
  code: (p: any) => <svg {...base(p)}><path d="M8 6l-5 6 5 6M16 6l5 6-5 6" /></svg>,
  drop: (p: any) => <svg {...base(p)}><path d="M12 3s6 6.3 6 11a6 6 0 0 1-12 0c0-4.7 6-11 6-11z" /></svg>,
  leaf: (p: any) => <svg {...base(p)}><path d="M5 19C5 9 13 4 20 4c0 8-5 15-15 15z" /><path d="M5 19c3-5 7-9 11-11" /></svg>,
  trophy: (p: any) => <svg {...base(p)}><path d="M8 4h8v5a4 4 0 0 1-8 0z" /><path d="M8 5H4c0 4 2 6 4 6M16 5h4c0 4-2 6-4 6M12 13v4M8 20h8M9 17h6" /></svg>,
  check: (p: any) => <svg {...base(p)}><path d="M4 12.5l5 5L20 6.5" /></svg>,
  spark: (p: any) => <svg {...base(p)}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" /></svg>,
  cal: (p: any) => <svg {...base(p)}><rect x="4" y="5" width="16" height="15" rx="2.5" /><path d="M4 10h16M8 3v4M16 3v4" /></svg>,
};

/* Deterministic daylight-lake scene per project id: sun + hills + water.
   Pure inline SVG, offline, no two projects look identical. */
export function ProjectArt({ id, h = 150 }: { id: string; h?: number }) {
  let n = 0;
  for (let i = 0; i < id.length; i++) n = (n * 31 + id.charCodeAt(i)) % 997;
  const hue = 190 + (n % 40);           // sky aqua range
  const sunX = 18 + (n % 64);
  const sunY = 22 + (n % 22);
  const hill = 62 + (n % 18);
  const hill2 = 74 + ((n >> 3) % 14);
  const gid = `g${id.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg viewBox="0 0 400 150" preserveAspectRatio="xMidYMid slice" style={{ width: "100%", height: h, display: "block" }} aria-hidden>
      <defs>
        <linearGradient id={`${gid}s`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`hsl(${hue} 80% 82%)`} />
          <stop offset=".62" stopColor={`hsl(${(hue + 24) % 360} 70% 90%)`} />
          <stop offset="1" stopColor="#f4fbf3" />
        </linearGradient>
        <linearGradient id={`${gid}w`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`hsl(${hue} 65% 72%)`} />
          <stop offset="1" stopColor={`hsl(${(hue + 50) % 360} 60% 88%)`} />
        </linearGradient>
        <radialGradient id={`${gid}sun`} cx=".5" cy=".5" r=".5">
          <stop offset="0" stopColor="#fffbe8" />
          <stop offset=".55" stopColor="#ffe9a8" />
          <stop offset="1" stopColor="rgba(255,214,110,0)" />
        </radialGradient>
      </defs>
      <rect width="400" height="150" fill={`url(#${gid}s)`} />
      <circle cx={sunX * 4} cy={sunY} r="30" fill={`url(#${gid}sun)`} />
      <circle cx={sunX * 4} cy={sunY} r="11" fill="#fff7d6" opacity=".95" />
      <ellipse cx="330" cy="26" rx="26" ry="9" fill="#fff" opacity=".8" />
      <ellipse cx="352" cy="32" rx="18" ry="7" fill="#fff" opacity=".65" />
      <path d={`M0 ${hill} Q 90 ${hill - 26} 190 ${hill - 6} T 400 ${hill + 4} V150 H0 Z`} fill={`hsl(${(hue + 90) % 360} 38% 62%)`} opacity=".9" />
      <path d={`M0 ${hill2} Q 120 ${hill2 - 22} 230 ${hill2 - 2} T 400 ${hill2 + 8} V150 H0 Z`} fill={`hsl(${(hue + 110) % 360} 42% 48%)`} />
      <rect y="112" width="400" height="38" fill={`url(#${gid}w)`} opacity=".92" />
      <ellipse cx={sunX * 4} cy="126" rx="26" ry="4.5" fill="#fff" opacity=".55" />
      <ellipse cx="120" cy="132" rx="60" ry="3" fill="#fff" opacity=".35" />
      <ellipse cx="300" cy="140" rx="80" ry="3.4" fill="#fff" opacity=".3" />
      <rect y="0" width="400" height="26" fill="#fff" opacity=".28" />
    </svg>
  );
}

/* Lake-scene backdrop for the landing hero. */
export function HeroScene() {
  return (
    <svg className="hero-scene" viewBox="0 0 1160 340" preserveAspectRatio="xMidYMax slice" aria-hidden>
      <defs>
        <radialGradient id="hsun" cx=".5" cy=".5" r=".5">
          <stop offset="0" stopColor="#fffbe8" /><stop offset=".5" stopColor="#ffedb0" />
          <stop offset="1" stopColor="rgba(255,214,110,0)" />
        </radialGradient>
      </defs>
      <circle cx="880" cy="70" r="90" fill="url(#hsun)" />
      <circle cx="880" cy="70" r="30" fill="#fff8dc" />
      <ellipse cx="980" cy="60" rx="70" ry="16" fill="#fff" opacity=".75" />
      <ellipse cx="1020" cy="78" rx="46" ry="11" fill="#fff" opacity=".55" />
      <ellipse cx="180" cy="48" rx="60" ry="13" fill="#fff" opacity=".6" />
      <path d="M0 208 Q 160 168 330 196 T 700 190 T 1160 200 V340 H0 Z" fill="#7cc9a2" opacity=".75" />
      <path d="M0 236 Q 200 200 420 226 T 860 222 T 1160 232 V340 H0 Z" fill="#3f9e78" opacity=".85" />
      <rect y="262" width="1160" height="78" fill="#0e7d90" opacity=".28" />
      <ellipse cx="880" cy="286" rx="70" ry="7" fill="#fff" opacity=".5" />
      <ellipse cx="420" cy="300" rx="150" ry="5" fill="#fff" opacity=".3" />
      <ellipse cx="140" cy="292" rx="90" ry="5" fill="#fff" opacity=".35" />
      <g fill="#0a4a56" opacity=".5">
        <ellipse cx="120" cy="238" rx="4" ry="9" /><ellipse cx="150" cy="236" rx="5" ry="12" />
        <ellipse cx="520" cy="232" rx="4" ry="9" /><ellipse cx="548" cy="230" rx="5" ry="12" />
      </g>
    </svg>
  );
}
