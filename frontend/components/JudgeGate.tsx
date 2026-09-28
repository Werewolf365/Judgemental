"use client";
import Link from "next/link";

/** Shown instead of participant flows (teams, submissions) to JUDGE-role
 *  accounts: judges score events, they never compete in them — registration
 *  is refused server-side, so these pages would only ever be dead ends. */
export default function JudgeGate() {
  return (
    <div className="card empty" style={{ maxWidth: 560, margin: "40px auto" }}>
      <h1>Judges don&apos;t compete</h1>
      <p>Your workspace is the judging console — teams and submissions belong to participants.</p>
      <Link href="/judge" className="btn">Open judging console</Link>
    </div>
  );
}
