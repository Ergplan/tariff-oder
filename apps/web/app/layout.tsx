import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import type { MeOut } from "@tariff/contracts";
import { PROFILE, apiTry } from "@/lib/api";

export const metadata: Metadata = {
  title: "Tariff Order Intelligence",
  description: "Evidence-backed Indian electricity tariff facts",
};

/**
 * Navigation follows who is signed in (ADR-0019): client members see the ARR workspace and the
 * library; the regulatory desk (reviewers, administrators) sees the reading and review tools
 * as well.  The API enforces every permission regardless of what a menu shows.
 */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await apiTry<MeOut>("/me");
  const role = me.data?.role;
  const desk = role === "reviewer" || role === "administrator" || (role === "analyst" && !(me.data?.organisations ?? []).length);
  const admin = role === "administrator";
  const client = (me.data?.organisations ?? []).length > 0 || admin;
  return (
    <html lang="en">
      <body>
        <header className="top">
          <span className="brand">Tariff Order Intelligence</span>
          <nav aria-label="Primary">
            {client ? <Link href="/client">ARR workspace</Link> : null}
            <Link href="/client/library">Library</Link>
            <Link href="/client/benchmarks">Benchmarks</Link>
            <Link href="/arr">ARR</Link>
            <Link href="/explorer">Explorer</Link>
            {desk ? (
              <>
                <Link href="/">Status</Link>
                <Link href="/commissions">Commissions</Link>
                <Link href="/sources">Source inbox</Link>
                <Link href="/review">Review</Link>
                <Link href="/jobs">Jobs</Link>
                <Link href="/registry">Registry</Link>
              </>
            ) : null}
            {admin ? (
              <>
                <Link href="/library">Library admin</Link>
                <Link href="/admin/organisations">Organisations</Link>
                <Link href="/admin/users">Users</Link>
              </>
            ) : null}
          </nav>
          <span className="badge" data-tone={PROFILE === "gcp" ? "ok" : "neutral"} title="Deployment profile">
            profile: {PROFILE}
          </span>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
