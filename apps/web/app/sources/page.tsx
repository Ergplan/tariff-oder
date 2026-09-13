import Link from "next/link";
import type { SourceList } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge, UnknownBadge } from "../components";
import { UploadForm } from "./upload-form";

export const dynamic = "force-dynamic";

export default async function SourcesPage() {
  const list = await apiTry<SourceList>("/sources?limit=200");
  return (
    <>
      <h1>Source inbox</h1>
      <p className="muted">
        Upload a tariff order PDF. Identical bytes are deduplicated by SHA-256. The worker inventories every page
        (text layer, labels, rotation); no number is extracted at this milestone.
      </p>
      <UploadForm />
      <h2>Registered sources</h2>
      {list.error ? <ErrorBanner error={list.error} /> : null}
      {list.data ? (
        list.data.total === 0 ? (
          <p className="muted">No sources registered.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Dataset</th>
                <th>State</th>
                <th>Pages</th>
                <th>Text layer</th>
                <th>SHA-256</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {list.data.items.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link href={`/sources/${s.id}`}>{s.original_filename}</Link>
                    {s.golden_id ? (
                      <div className="muted">
                        golden manifest: <code>{s.golden_id}</code>
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <DatasetBadge kind={s.dataset_kind} />
                  </td>
                  <td>
                    <StateBadge state={s.state} />
                  </td>
                  <td>{s.page_count ?? <UnknownBadge label="pages" />}</td>
                  <td>
                    {s.pages_with_text == null ? (
                      <UnknownBadge label="text layer" />
                    ) : (
                      <>
                        {s.pages_with_text} with / {s.pages_without_text} without
                      </>
                    )}
                  </td>
                  <td className="mono">{s.sha256.slice(0, 16)}…</td>
                  <td>
                    <span className="muted">{s.uploaded_by}</span>
                    <br />
                    <span className="muted">{new Date(s.acquired_at).toLocaleString()}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : null}
    </>
  );
}
