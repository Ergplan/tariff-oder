import Link from "next/link";
import type { SourceList, SourceState } from "@tariff/contracts";
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
        Every registered tariff order and where it stands. Open a source to see what it needs next; the source page leads
        with the one action that is yours.
      </p>
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
                <th>Next</th>
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
                  <td>{nextStep(s.state, s.id)}</td>
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
      <h2>Upload</h2>
      <p className="muted">
        Upload a tariff order PDF. Identical bytes are deduplicated by SHA-256; the pipeline starts at inventory.
      </p>
      <UploadForm />
    </>
  );
}

/** The reader's next step per state — the same rule the source page uses for its banner. */
function nextStep(state: SourceState, id: string) {
  switch (state) {
    case "localised":
      return (
        <Link href={`/sources/${id}#checkpoint`}>
          <span className="badge" data-tone="warn">reviewer: confirm localisation</span>
        </Link>
      );
    case "awaiting_review":
      return (
        <Link href={`/sources/${id}/review`}>
          <span className="badge" data-tone="warn">reviewer: decide candidates</span>
        </Link>
      );
    case "published":
      return (
        <Link href={`/explorer/${id}`}>
          <span className="badge" data-tone="ok">published: explore</span>
        </Link>
      );
    case "failed":
    case "cancelled":
    case "rejected":
    case "superseded":
    case "needs_reprocessing":
      return <span className="badge" data-tone="bad">{state.replace(/_/g, " ")}</span>;
    default:
      return <span className="muted">worker: next stage</span>;
  }
}
