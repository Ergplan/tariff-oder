import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "ARR Network", template: "%s · ARR Network" },
  description: "ARR orders of India's electricity distribution and transmission utilities, read into a database: every figure with its page and the line as printed.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <a className="skip" href="#main">Skip to content</a>
        <header className="top">
          <a className="brand" href="/">
            <b>ARR Network</b>
            <span>Revenue requirements of India&apos;s power utilities, read from the orders</span>
          </a>
          <nav aria-label="Sections">
            <a href="/">Map</a>
            <a href="/search">Search</a>
            <a href="/ask">Ask</a>
            <a href="/agents">Agents</a>
          </nav>
        </header>
        <main id="main">{children}</main>
        <footer className="foot">
          <span>Machine-read from the orders; not reviewed by a person unless a figure is marked &ldquo;reviewed by a person&rdquo;. Check the page before relying on a figure.</span>
          <span><a href="/api/v1/states">JSON API</a></span>
        </footer>
      </body>
    </html>
  );
}
