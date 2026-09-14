import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { PROFILE } from "@/lib/api";

export const metadata: Metadata = {
  title: "Tariff Order Intelligence",
  description: "Evidence-backed Indian electricity tariff facts",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="top">
          <span className="brand">Tariff Order Intelligence</span>
          <nav aria-label="Primary">
            <Link href="/">Status</Link>
            <Link href="/sources">Source inbox</Link>
            <Link href="/review">Review</Link>
            <Link href="/jobs">Jobs</Link>
            <Link href="/registry">Registry</Link>
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
