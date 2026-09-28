import Header from "@/components/Header";
import "./globals.css";

export const metadata = {
  title: "Dogfood — Hackathon Portal",
  description: "Run hackathons locally: events, teams, submissions, gallery.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="aero-field" aria-hidden>
          <span className="orb orb-a" />
          <span className="orb orb-b" />
          <span className="orb orb-c" />
        </div>
        <Header />
        <main className="container">{children}</main>
        <footer className="site-footer">
          <div className="footer-inner">
            <b style={{ color: "var(--sea-950)" }}>Dogfood</b>
            <span>Self-hosted hackathon portal · runs offline</span>
            <span style={{ marginLeft: "auto" }}>
              <a href="/events">Events</a> · Local-first
            </span>
          </div>
        </footer>
      </body>
    </html>
  );
}
