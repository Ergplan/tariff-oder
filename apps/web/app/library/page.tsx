import Link from "next/link";
import type { LibraryEntryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";
import { ActionButton } from "../client/actions";
import { KIND_SHORT, Level } from "../client/levels";
import { DiscoverForm, EntryForm, SeedForm } from "./library-admin";

export const dynamic = "force-dynamic";

/**
 * Library administration (desk, ADR-0019): seed the expected documents, record official
 * URLs, acquire them (the worker fetches and registers each PDF exactly as an upload), and
 * see what failed.  Acquisition needs a host whose network reaches the commission's site.
 */
export default async function LibraryAdmin({ searchParams }: { searchParams: Promise<{ status?: string; commission?: string }> }) {
  const sp = await searchParams;
  const q = new URLSearchParams();
  if (sp.status) q.set("status", sp.status);
  if (sp.commission) q.set("commission", sp.commission);
  q.set("limit", "300");
  const [res, profiles] = await Promise.all([apiTry<LibraryEntryOut[]>(`/library/entries?${q.toString()}`), apiTry<string[]>("/library/discovery-profiles")]);
  return (
    <>
      <h1>Library administration</h1>
      <p className="muted">
        Clients see the library at <Link href="/client/library">/client/library</Link>. Expected slots are expectations from the registry; a document is only as good as its official source.
      </p>
      <h2>Seed expected documents</h2>
      <SeedForm />
      <h2>Find documents on a commission&apos;s website</h2>
      <DiscoverForm profiles={profiles.data ?? []} />
      <h2>Record a document</h2>
      <EntryForm />
      <h2>Entries</h2>
      <p>
        Show: <Link href="/library">all</Link> · <Link href="/library?status=located">located</Link> · <Link href="/library?status=failed">failed</Link> · <Link href="/library?status=acquired">acquired</Link> ·{" "}
        <Link href="/library?status=expected">expected</Link>
      </p>
      {res.error ? (
        <ErrorBanner error={res.error} />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Commission / licensee</th>
                <th>Document</th>
                <th>Level</th>
                <th>URL</th>
                <th>Attempts</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(res.data ?? []).map((e) => (
                <tr key={e.id}>
                  <td>
                    {e.commission} {e.utility ? `/ ${e.utility}` : ""}
                  </td>
                  <td>
                    {KIND_SHORT[e.document_kind] ?? e.document_kind} {e.fiscal_year || "(current)"}
                    {e.title ? <div className="muted">{e.title}</div> : null}
                  </td>
                  <td>
                    <Level level={e.reading ?? e.status} />
                    {e.last_error ? <div className="muted">{e.last_error}</div> : null}
                  </td>
                  <td className="muted" style={{ maxWidth: "22rem", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {e.url ?? "—"}
                  </td>
                  <td>{e.attempts}</td>
                  <td>{e.url && e.status !== "acquired" ? <ActionButton path={`library/entries/${e.id}/acquire`} label="Acquire" tone="plain" /> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
