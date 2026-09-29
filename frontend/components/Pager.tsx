"use client";

/** Shared client-side pager: 10 entries per page, newest first where the
 *  data carries a timestamp, Previous/Next Google-style navigation.
 *  Matches the audit-log pager idiom (btn-ghost btn-sm + "Showing x–y of n").
 *  Client-side by design: these lists are small and already fully loaded,
 *  so paging is pure presentation — no new requests, no lag. */
export const PAGE_SIZE = 10;

export function paginate<T>(list: T[], page: number): T[] {
  const p = Math.max(1, page);
  return list.slice((p - 1) * PAGE_SIZE, p * PAGE_SIZE);
}

export function Pager({ page, total, onPage }: {
  page: number; total: number; onPage: (p: number) => void;
}) {
  if (total <= PAGE_SIZE) return null;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const p = Math.min(Math.max(1, page), pages);
  const from = (p - 1) * PAGE_SIZE + 1;
  const to = Math.min(p * PAGE_SIZE, total);
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", justifyContent: "flex-end", marginTop: 12, flexWrap: "wrap" }}>
      <button className="btn-ghost btn-sm" disabled={p <= 1} onClick={() => onPage(p - 1)}>← Previous</button>
      <span style={{ fontSize: 13, color: "var(--muted)" }}>Showing {from}–{to} of {total}</span>
      <button className="btn-ghost btn-sm" disabled={p >= pages} onClick={() => onPage(p + 1)}>Next →</button>
    </div>
  );
}
