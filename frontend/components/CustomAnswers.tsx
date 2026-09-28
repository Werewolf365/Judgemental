"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Renders an event's organizer-defined submission questions.
 *  value: {field_id: answer}. onChange receives the updated record. */
export default function CustomAnswers({
  eventId, value, onChange, disabled,
}: {
  eventId: string; value: Record<string, string>; onChange: (v: Record<string, string>) => void; disabled?: boolean;
}) {
  const [fields, setFields] = useState<any[]>([]);
  useEffect(() => {
    if (!eventId) { setFields([]); return; }
    api(`/events/${eventId}/form-fields`).then((d) => setFields(d.fields || [])).catch(() => setFields([]));
  }, [eventId]);
  if (!fields.length) return null;

  function set(id: string, v: string) {
    onChange({ ...value, [id]: v });
  }

  return (
    <div>
      <h2>Event questions</h2>
      <p style={{ color: "var(--muted)", fontSize: 14 }}>Added by the organizer for this event.</p>
      {fields.map((f) => (
        <div key={f.id}>
          <label>{f.label}{f.required ? " *" : ""}</label>
          {f.field_type === "textarea" && (
            <textarea value={value[f.id] || ""} disabled={disabled} onChange={(e) => set(f.id, e.target.value)} />
          )}
          {f.field_type === "number" && (
            <input type="number" value={value[f.id] || ""} disabled={disabled} onChange={(e) => set(f.id, e.target.value)} />
          )}
          {f.field_type === "url" && (
            <input value={value[f.id] || ""} disabled={disabled} onChange={(e) => set(f.id, e.target.value)} placeholder="https://…" inputMode="url" />
          )}
          {f.field_type === "select" && (
            <select value={value[f.id] || ""} disabled={disabled} onChange={(e) => set(f.id, e.target.value)}>
              <option value="">— pick —</option>
              {(f.options || []).map((o: string) => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
          {(f.field_type === "text" || !["textarea", "number", "url", "select"].includes(f.field_type)) && (
            <input value={value[f.id] || ""} disabled={disabled} onChange={(e) => set(f.id, e.target.value)} maxLength={2000} />
          )}
        </div>
      ))}
    </div>
  );
}
