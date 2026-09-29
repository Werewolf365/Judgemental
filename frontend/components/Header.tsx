"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchMe, logout, initials, type Me } from "@/lib/api";

export default function Header() {
  const [me, setMe] = useState<Me | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => { fetchMe().then(setMe); }, [path]);
  useEffect(() => { setOpen(false); }, [path]);

  const isOrg = me && (me.role === "ORGANIZER" || me.role === "ADMIN");
  const isJudge = me?.role === "JUDGE";
  // Organizers run events rather than compete: Dashboard is their mission
  // control and they have no team flow, so "My teams" would be a dead end.
  // Judges have their own console for the same reason: the participant
  // workspace (teams, submissions) cannot work for an account that is
  // refused event registration server-side.
  const showTeams = me && !isOrg && !isJudge;
  const link = (href: string, label: string) => (
    <Link key={href} href={href} className={path === href || path.startsWith(href + "/") ? "active" : ""}>{label}</Link>
  );

  return (
    <header className="site-header">
      <div className="wrap-pad" style={{ padding: 0 }}>
        <div className="header-inner">
          <Link href="/" className="brand">
            <span className="brand-mark">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M12 3s6 6.3 6 11a6 6 0 0 1-12 0c0-4.7 6-11 6-11z" />
                <path d="M9.5 14a2.6 2.6 0 0 0 2.4 2.7" strokeOpacity=".9" />
              </svg>
            </span>
            Dogfood
          </Link>
          <nav className={`main-nav${open ? " open" : ""}`} aria-label="Primary">
            {link("/events", "Events")}
            {me && !isJudge && link("/dashboard", isOrg ? "Overview" : "Dashboard")}
            {showTeams && link("/teams", "My teams")}
            {isOrg && link("/organizer", "Organize")}
            {isOrg && link("/security", "Security")}
            {isJudge && link("/judge", "Judging")}
            {me?.role === "ADMIN" && link("/admin", "Admin")}
          </nav>
          <div className="header-right">
            <button className="nav-toggle" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}
              onClick={() => setOpen((o) => !o)}>☰</button>
            {me === undefined ? null : me === null ? (
              <>
                <Link href="/login" className="btn-ghost btn-sm">Log in</Link>
                <Link href="/register" className="btn btn-sm">Get started</Link>
              </>
            ) : (
              <>
                <Link href="/settings" className="user-chip" title={`${me.email} — account settings`} style={{ textDecoration: "none", color: "inherit" }}>
                  {(me as any).avatar_url
                    ? <img src={(me as any).avatar_url} alt="" width={28} height={28} style={{ borderRadius: "50%", objectFit: "cover" }} />
                    : <span className="avatar">{initials(me.display_name)}</span>}
                  {me.display_name}
                  <span className="badge badge-muted">{me.role}</span>
                </Link>
                <button className="link-btn" onClick={logout}>Log out</button>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
