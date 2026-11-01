import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import type { MeOut } from "@tariff/contracts";
import { PROFILE, apiTry } from "@/lib/api";
import NavMenu from "./nav-menu";

export const metadata: Metadata = {
  title: "Tariff Order Studio",
  description: "Evidence-backed Indian electricity tariff facts and ARR petitions",
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
          <Link href={client ? "/client" : "/"} className="brand" style={{ textDecoration: "none" }}>
            Tariff Order Studio
          </Link>
          <nav aria-label="Primary">
            {client ? <Link href="/client">Petition studio</Link> : null}
            <Link href="/client/library">Library</Link>
            <Link href="/client/benchmarks">Benchmarks</Link>
            <Link href="/arr">ARR</Link>
            <Link href="/explorer">Explorer</Link>
            {desk ? (
              <NavMenu
                label="Desk"
                links={[
                  { href: "/", label: "Status" },
                  { href: "/arr/readings", label: "ARR readings" },
                  { href: "/review", label: "Review" },
                  { href: "/sources", label: "Source inbox" },
                  { href: "/commissions", label: "Commissions" },
                  { href: "/jobs", label: "Jobs" },
                  { href: "/registry", label: "Registry" },
                ]}
              />
            ) : null}
            {admin ? (
              <NavMenu
                label="Admin"
                links={[
                  { href: "/library", label: "Library admin" },
                  { href: "/admin/organisations", label: "Organisations" },
                  { href: "/admin/users", label: "Users" },
                ]}
              />
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
