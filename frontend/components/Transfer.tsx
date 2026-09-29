"use client";
import { useState } from "react";
import { createPortal } from "react-dom";

/** Organizer-only bulk transfer dialog: pick export datasets (or all) and
 *  download one ZIP; upload a CSV to import organizer-owned setup data.
 *  Rendered through a portal like Popup, but with its own wider panel
 *  because a 14-item checklist does not fit a confirmation dialog. */
const DATASETS: [string, string][] = [
  ["participants", "Participants (+ registration details)"],
  ["organizers", "Organizers"],
  ["judges", "Judges (roster + loads)"],
  ["tracks", "Tracks"],
  ["prizes", "Prizes"],
  ["rubric", "Rubric"],
  ["teams", "Teams (+ members)"],
  ["projects", "Projects"],
  ["evaluations", "Evaluations (per-criterion scores)"],
  ["assignments", "Assignments"],
  ["ballots", "Ballots (votes)"],
  ["comments", "Comments"],
  ["results", "Results (latest rankings)"],
  ["audit", "Audit trail"],
];
const IMPORTABLE: [string, string][] = [
  ["tracks", "Tracks — columns: name"],
  ["prizes", "Prizes — columns: name, description, value, track, display_order"],
  ["rubric", "Rubric — columns: name, description, weight, scale_lo, scale_hi"],
  ["judges", "Judges — column: email (must already hold the judge role)"],
  ["organizers", "Organizers — column: email (must already hold the organizer role)"],
];

export default function Transfer({ eventId, onClose }: { eventId: string; onClose: () => void }) {
  const [sel, setSel] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(DATASETS.map(([k]) => [k, true])));
  const [impDs, setImpDs] = useState("tracks");
  const [impMsg, setImpMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const all = DATASETS.every(([k]) => sel[k]);
  const picked = DATASETS.filter(([k]) => sel[k]).map(([k]) => k);

  async function doImport(file: File | undefined) {
    if (!file) return;
    setImpMsg(""); setBusy(true);
    try {
      const fd = new FormData();
      fd.append("dataset", impDs);
      fd.append("file", file);
      const res = await fetch(`/api/events/${eventId}/import`, {
        method: "POST", credentials: "include", body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail?.message || `Import failed (${res.status})`);
      setImpMsg(`Imported ${data.dataset}: ${data.created} created, ${data.skipped} skipped.` +
        (data.errors?.length ? ` First issues: ${data.errors.slice(0, 3).join(" · ")}` : ""));
    } catch (e: any) { setImpMsg(e.message); }
    finally { setBusy(false); }
  }

  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="popup-overlay" role="presentation"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="popup-panel card" role="dialog" aria-modal="true" aria-label="Import and export"
        style={{ maxWidth: 560, background: "#fff" }}>
        <div style={{ flex: "1 1 100%" }}>
          <h3 style={{ marginTop: 0 }}>Import / Export</h3>
          <p className="form-note" style={{ marginTop: 0 }}>
            Export downloads one ZIP of CSVs — every metric on this event. Import adds
            setup rows from a CSV (duplicates skipped, roster rules enforced). Organizers only.</p>
          <h4 style={{ marginBottom: 6 }}>Export datasets</h4>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 14, fontWeight: 700 }}>
            <input type="checkbox" checked={all} style={{ width: "auto", margin: 0 }}
              onChange={(e) => setSel(Object.fromEntries(DATASETS.map(([k]) => [k, e.target.checked])))} />
            Select all records
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 12px", margin: "8px 0 12px" }}>
            {DATASETS.map(([k, label]) => (
              <label key={k} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13.5, fontWeight: 400 }}>
                <input type="checkbox" checked={!!sel[k]} style={{ width: "auto", margin: 0 }}
                  onChange={(e) => setSel((s) => ({ ...s, [k]: e.target.checked }))} />
                {label}
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <a className="btn btn-sm"
              href={picked.length ? `/api/events/${eventId}/export?datasets=${picked.join(",")}` : undefined}
              download aria-disabled={!picked.length}
              style={!picked.length ? { opacity: .5, pointerEvents: "none" } : undefined}>
              Download{all ? " all" : ` ${picked.length} dataset${picked.length === 1 ? "" : "s"}`} (ZIP)</a>
          </div>
          <h4 style={{ marginBottom: 6, marginTop: 16 }}>Import CSV</h4>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: "1 1 220px" }}><label style={{ display: "block", marginBottom: 6 }}>Dataset</label>
              <select value={impDs} onChange={(e) => setImpDs(e.target.value)} style={{ marginBottom: 0 }}>
                {IMPORTABLE.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
              </select></div>
            <label className="btn btn-sm" style={{ cursor: "pointer" }}>
              Choose CSV…
              <input type="file" accept=".csv,text/csv" hidden disabled={busy}
                onChange={(e) => { doImport(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
          </div>
          {impMsg && <p role="status" style={{ marginBottom: 0 }}>{impMsg}</p>}
        </div>
        <div style={{ marginLeft: "auto" }}><button className="btn btn-sm" onClick={onClose}>Done</button></div>
      </div>
    </div>,
    document.body,
  );
}
