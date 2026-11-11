import { headers } from "next/headers";

/** This site's origin for permanent links: SITE_URL when set, else the request's host. */
export async function siteOrigin(): Promise<string> {
  if (process.env.SITE_URL) return process.env.SITE_URL.replace(/\/$/, "");
  const h = await headers();
  const host = h.get("x-forwarded-host") || h.get("host") || "localhost";
  const proto = h.get("x-forwarded-proto") || (/^(localhost|127\.)/.test(host) ? "http" : "https");
  return `${proto}://${host}`;
}
