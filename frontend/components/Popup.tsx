"use client";
import { useEffect } from "react";
import { createPortal } from "react-dom";

export type PopupKind = "ok" | "info" | "warn";

/** A small centered confirmation dialog.
 *
 *  Used for one-shot feedback where an inline message is too easy to miss —
 *  most importantly "your event is published", which is the moment the
 *  organizer has been working toward. It closes on the button, on a click
 *  outside the panel, and on Escape, so it can never trap the page.
 */
export default function Popup({
  kind = "ok", title, children, onClose, dismissLabel = "Close",
}: {
  kind?: PopupKind;
  title: string;
  children?: React.ReactNode;
  onClose: () => void;
  dismissLabel?: string;
}) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") onClose(); }
    document.addEventListener("keydown", onKey);
    // Lock the page behind the dialog so the wheel does not scroll away.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  if (typeof document === "undefined") return null;
  const tone = kind === "warn" ? "badge-warn" : kind === "info" ? "badge-track" : "badge-ok";
  const pip = kind === "warn" ? "pip-amber" : kind === "info" ? "pip-amber" : "pip-green";
  const glyph = kind === "warn" ? "!" : kind === "info" ? "i" : "✓";

  return createPortal(
    <div className="popup-overlay" role="presentation"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="popup-panel card" role="alertdialog" aria-modal="true" aria-label={title}>
        <span className={`popup-glyph ${tone}`} aria-hidden>{glyph}</span>
        <div>
          <h3 style={{ margin: 0 }}>{title}</h3>
          {children && <div className="popup-body">{children}</div>}
        </div>
        <button className="btn btn-sm" onClick={onClose} style={{ marginLeft: "auto" }}>{dismissLabel}</button>
      </div>
    </div>,
    document.body,
  );
}
