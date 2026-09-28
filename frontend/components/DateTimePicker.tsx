"use client";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const MONTHS = ["January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December"];
const DAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
const MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

type Parts = { y: number; m: number; d: number; hh: number; mm: number };

function parseLocal(v: string): Parts | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(v || "");
  if (!m) return null;
  return { y: +m[1], m: +m[2] - 1, d: +m[3], hh: +m[4], mm: +m[5] };
}

function toLocal(p: Parts): string {
  const q = (n: number) => String(n).padStart(2, "0");
  return `${p.y}-${q(p.m + 1)}-${q(p.d)}T${q(p.hh)}:${q(p.mm)}`;
}

function formatUTC(p: Parts): string {
  const dt = new Date(Date.UTC(p.y, p.m, p.d, p.hh, p.mm));
  const ap = p.hh >= 12 ? "PM" : "AM";
  const h12 = p.hh % 12 === 0 ? 12 : p.hh % 12;
  const q = (n: number) => String(n).padStart(2, "0");
  return `${q(dt.getUTCDate())} ${MONTH_SHORT[p.m]} ${p.y}, ${h12}:${q(p.mm)} ${ap} UTC`;
}

function daysInMonth(y: number, m: number) {
  return new Date(y, m + 1, 0).getDate();
}

/** Glassy Frutiger-Aero date+time picker. Value is a local "YYYY-MM-DDTHH:mm"
 *  string (interpreted as UTC by the backend), "" when unset.
 *  With defaultToday, opening an empty field pre-selects today (caller's
 *  onChange fires once) instead of leaving the field blank — use it for
 *  deadline fields where "today" is the sane starting point, never for
 *  fields where an empty value means "no restriction". */
export default function DateTimePicker({
  value, onChange, placeholder = "Pick date & time", defaultToday = false,
}: {
  value: string; onChange: (v: string) => void; placeholder?: string;
  defaultToday?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const now = new Date();
  const cur = parseLocal(value);
  const [vy, setVy] = useState(cur?.y ?? now.getFullYear());
  const [vm, setVm] = useState(cur?.m ?? now.getMonth());
  const [sel, setSel] = useState<Parts | null>(cur);
  const [hh, setHh] = useState(cur?.hh ?? 18);
  const [mm, setMm] = useState(cur?.mm ?? 0);
  const boxRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  function place() {
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const w = 320;
    // Measured height once rendered; estimate covers header + grid + time + footer.
    const h = popRef.current?.offsetHeight || 440;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
    let top = r.bottom + 8;
    // Flip above the field when there is no room below (native-picker behavior).
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 8);
    setPos({ top, left });
  }

  useEffect(() => {
    if (!open) return;
    if (!parseLocal(value)) {
      // Nothing selected: always open on today's month, never on whatever
      // month the view was left at (e.g. after Clear).
      const n = new Date();
      setVy(n.getFullYear()); setVm(n.getMonth());
    }
    if (defaultToday && !parseLocal(value)) {
      const n = new Date();
      const p = { y: n.getFullYear(), m: n.getMonth(), d: n.getDate(), hh, mm };
      setVy(p.y); setVm(p.m); setSel(p);
      onChange(toLocal(p));
    }
    place();
    // Second pass after paint, so the flip uses the measured height.
    const raf = requestAnimationFrame(place);
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (boxRef.current?.contains(t)) return;
      if (popRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setOpen(false); }
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open ]);

  useEffect(() => {
    const c = parseLocal(value);
    setSel(c);
    if (c) { setVy(c.y); setVm(c.m); setHh(c.hh); setMm(c.mm); }
    else {
      // Cleared: park the view on today so the next open starts sane.
      const n = new Date();
      setVy(n.getFullYear()); setVm(n.getMonth());
    }
  }, [value]);

  function pickDay(d: number) {
    const p = { y: vy, m: vm, d, hh, mm };
    setSel(p);
    onChange(toLocal(p));
  }
  function pickTime(nh: number, nm: number) {
    setHh(nh); setMm(nm);
    if (sel) { const p = { ...sel, hh: nh, mm: nm }; setSel(p); onChange(toLocal(p)); }
  }
  function today() {
    const n = new Date();
    const p = { y: n.getFullYear(), m: n.getMonth(), d: n.getDate(), hh, mm };
    setVy(p.y); setVm(p.m); setSel(p);
    onChange(toLocal(p));
  }
  function clear() {
    setSel(null); onChange("");
    const n = new Date();
    setVy(n.getFullYear()); setVm(n.getMonth());
  }

  function stepMonth(dir: number) {
    let y = vy, m = vm + dir;
    if (m < 0) { m = 11; y--; }
    if (m > 11) { m = 0; y++; }
    setVy(y); setVm(m);
  }

  const first = new Date(vy, vm, 1).getDay();
  const total = daysInMonth(vy, vm);
  const cells: (number | null)[] = [...Array(first).fill(null), ...Array.from({ length: total }, (_, i) => i + 1)];
  while (cells.length % 7) cells.push(null);
  const isToday = (d: number) => vy === now.getFullYear() && vm === now.getMonth() && d === now.getDate();
  const isSel = (d: number) => !!sel && sel.y === vy && sel.m === vm && sel.d === d;

  return (
    <div ref={boxRef}>
      <button
        ref={btnRef}
        type="button" onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open}
        style={{
          width: "100%", textAlign: "left", font: "inherit", fontSize: 14.5,
          padding: "11px 14px", borderRadius: 13, cursor: "pointer",
          border: "1px solid rgba(255,255,255,.9)", outline: "1px solid rgba(10,74,86,.2)",
          background: "rgba(255,255,255,.9)", color: sel ? "var(--ink)" : "var(--muted)",
          boxShadow: "inset 0 2px 5px rgba(6,80,95,.07)",
        }}
      >
        {sel ? formatUTC(sel) : placeholder} <span style={{ float: "right" }}>▾</span>
      </button>
      {open && typeof document !== "undefined" && createPortal(
        <div ref={popRef} role="dialog" aria-label="Choose date and time"
          className="card"
          style={{ position: "fixed", zIndex: 500, top: pos.top, left: pos.left, width: "min(320px, calc(100vw - 16px))", margin: 0, padding: 16 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ display: "flex", alignItems: "center", marginBottom: 8, gap: 4 }}>
            <select aria-label="Month" value={vm}
              onChange={(e) => setVm(+e.target.value)}
              style={{ font: "inherit", fontWeight: 800, fontSize: 15, padding: "4px 6px", borderRadius: 9, border: "1px solid var(--line)", background: "#fff", maxWidth: 118 }}>
              {MONTHS.map((label, i) => <option key={label} value={i}>{label}</option>)}
            </select>
            <select aria-label="Year" value={vy}
              onChange={(e) => setVy(+e.target.value)}
              style={{ font: "inherit", fontWeight: 800, fontSize: 15, padding: "4px 6px", borderRadius: 9, border: "1px solid var(--line)", background: "#fff", maxWidth: 84 }}>
              {Array.from({ length: 51 }, (_, i) => 2000 + i).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <span style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
              <button type="button" className="btn-ghost btn-sm" onClick={() => stepMonth(-1)} aria-label="Previous month">‹</button>
              <button type="button" className="btn-ghost btn-sm" onClick={() => stepMonth(1)} aria-label="Next month">›</button>
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2, textAlign: "center", fontSize: 12, fontWeight: 700, color: "var(--muted)", marginBottom: 4 }}>
            {DAYS.map((d) => <span key={d}>{d}</span>)}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 2 }}>
            {cells.map((d, i) => d === null ? <span key={i} /> : (
              <button
                key={i} type="button" onClick={() => pickDay(d)}
                aria-label={`${d} ${MONTHS[vm]} ${vy}`}
                style={{
                  border: isSel(d) ? "1px solid rgba(2,110,130,.55)" : isToday(d) ? "1px solid var(--aqua)" : "1px solid transparent",
                  borderRadius: "50%", width: 34, height: 34, margin: "0 auto", cursor: "pointer",
                  font: "inherit", fontSize: 13.5, fontWeight: isSel(d) ? 800 : 500,
                  color: isSel(d) ? "#fff" : "var(--ink)",
                  background: isSel(d)
                    ? "radial-gradient(circle at 35% 28%, #5fd8e8 0%, #00b8cc 55%, #008ba0 100%)"
                    : "transparent",
                  boxShadow: isSel(d) ? "0 3px 10px rgba(0,147,173,.4), inset 0 1px 0 rgba(255,255,255,.7)" : "none",
                }}
              >{d}</button>
            ))}
          </div>
          <div style={{ marginTop: 12 }}>
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--muted)" }}>Time</span>
              <select aria-label="Hour" value={hh} onChange={(e) => pickTime(+e.target.value, mm)}
                style={{ font: "inherit", padding: "6px 8px", borderRadius: 9, border: "1px solid var(--line)", background: "#fff" }}>
                {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}</option>)}
              </select>
              <b style={{ color: "var(--muted)" }}>:</b>
              <select aria-label="Minute" value={mm} onChange={(e) => pickTime(hh, +e.target.value)}
                style={{ font: "inherit", padding: "6px 8px", borderRadius: 9, border: "1px solid var(--line)", background: "#fff" }}>
                {[0, 15, 30, 45].map((m) => <option key={m} value={m}>{String(m).padStart(2, "0")}</option>)}
              </select>
            </div>
            <div style={{ display: "flex", gap: 4, alignItems: "center", marginTop: 10 }}>
              <button type="button" className="link-btn" style={{ padding: "8px 6px" }} onClick={clear}>Clear</button>
              <button type="button" className="link-btn" style={{ padding: "8px 6px" }} onClick={today}>Today</button>
              <button type="button" className="btn btn-sm" style={{ marginLeft: "auto" }} onClick={() => setOpen(false)}>Done</button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
