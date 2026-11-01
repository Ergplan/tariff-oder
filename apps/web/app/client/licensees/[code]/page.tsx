import Link from "next/link";
import type { LibraryEntryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { KIND_SHORT, Level } from "../../levels";

export const dynamic = "force-dynamic";

/**
 * One licensee in the client application: its documents in the library (with the official
 * link and how far each has been read), a link to its reviewed ARR history, and the way in
 * to start an ARR process for it.
 */
export default async function LicenseePage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const name = decodeURIComponent(code);
  const res = await apiTry<LibraryEntryOut[]>(`/library/entries?utility=${encodeURIComponent(name)}`);
  if (res.error) return <ErrorBanner error={res.error} />;
  const entries = [...(res.data ?? [])].sort((a, b) => (b.fiscal_year || "~").localeCompare(a.fiscal_year || "~") || a.document_kind.localeCompare(b.document_kind));
  return (
    <>
      <p>
        <Link href="/client/library">← Library</Link>
      </p>
      <h1>
        {name} <span className="muted">· documents and ARR</span>
      </h1>
      <p>
        <Link href={`/client/cases/new?utility=${encodeURIComponent(name)}`}>Start an ARR process for {name} →</Link> · <Link href={`/arr/${encodeURIComponent(name)}`}>Reviewed ARR history →</Link> · <Link href={`/client/benchmarks?highlight=${encodeURIComponent(name)}`}>Benchmarks →</Link>
      </p>
      <h2>Documents</h2>
      {entries.length === 0 ? (
        <p className="muted">No document of this licensee is in the library yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Year</th>
                <th>Document</th>
                <th>Level</th>
                <th>Official source</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="mono">{e.fiscal_year || "current period"}</td>
                  <td>
                    {KIND_SHORT[e.document_kind] ?? e.document_kind}
                    {e.title ? <div className="muted">{e.title}</div> : null}
                  </td>
                  <td>
                    <Level level={e.reading ?? e.status} />
                  </td>
                  <td>
                    {e.url ? (
                      <a href={e.url} rel="noreferrer noopener" target="_blank">
                        commission website
                      </a>
                    ) : (
                      <span className="muted">not located</span>
                    )}
                    {e.source_id ? (
                      <div>
                        <Link href={`/sources/${e.source_id}`}>registered copy</Link>
                      </div>
                    ) : null}
                  </td>
                  <td className="muted">{e.last_error ?? e.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
