import { Fragment } from "react";
import Link from "next/link";
import type { RegistryOut, SourceList, SourceState , SourceSummary } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, StateBadge, UnknownBadge } from "../components";
import { UploadForm } from "./upload-form";

export const dynamic = "force-dynamic";

export default async function SourcesPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const qs = new URLSearchParams({ limit: "200" });
  for (const k of ["commission", "utility", "assigned"]) if (typeof sp[k] === "string" && sp[k]) qs.set(k, sp[k] as string);
  const [list, registry] = await Promise.all([apiTry<SourceList>(`/sources?${qs.toString()}`), apiTry<RegistryOut>("/registry")]);
  return (
    <>
      <h1>Source inbox</h1>
      {qs.has("commission") || qs.has("utility") || qs.has("assigned") ? (
        <p className="muted">
          Filtered: {[qs.get("commission"), qs.get("utility"), qs.get("assigned")].filter(Boolean).join(" · ")} ·{" "}
          <Link href="/sources">show all</Link>
        </p>
      ) : null}
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
                <th>Commission · utility</th>
                <th>Reviewer</th>
                <th>Pages</th>
                <th>Next</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {groupByCommission(list.data.items).map((g) => (
                <Fragment key={g.key}>
                  <tr className="group-row">
                    <td colSpan={8}>
                      <strong>{g.title}</strong> <span className="muted">· {g.items.length} order{g.items.length === 1 ? "" : "s"}</span>
                      {g.code ? (
                        <>
                          {" · "}
                          <Link href={`/commissions#${g.code}`}>commission</Link>
                        </>
                      ) : null}
                    </td>
                  </tr>
                  {g.items.map((s) => (
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
                  <td>
                    {s.commission_code ? (
                      <>
                        <Link href={`/sources?commission=${encodeURIComponent(s.commission_code)}`}>{s.commission_code}</Link> ·{" "}
                        <span className="mono">{s.utility_code}</span>
                      </>
                    ) : (
                      <span className="muted">not set</span>
                    )}
                  </td>
                  <td>{s.assigned_to ?? <span className="muted">—</span>}</td>
                  <td>{s.page_count ?? <UnknownBadge label="pages" />}</td>
                  <td>{nextStep(s.state, s.id)}</td>
                  <td>
                    <span className="muted">{s.uploaded_by}</span>
                    <br />
                    <span className="muted">{new Date(s.acquired_at).toLocaleString()}</span>
                  </td>
                </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        )
      ) : null}
      <h2>Upload</h2>
      <p className="muted">
        Upload a tariff order PDF under its distribution company (choose it on the <Link href="/commissions">Commissions</Link> page to
        land here with it selected). Identical bytes are deduplicated by SHA-256; the pipeline starts at inventory.
      </p>
      <div id="upload" />
      <UploadForm utilities={registry.data?.utilities ?? []} preselect={typeof sp.utility === "string" ? sp.utility : undefined} />
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

/** Orders grouped by commission, alphabetically; orders without a utility last. */
function groupByCommission(items: SourceSummary[]) {
  const groups = new Map<string, { key: string; code: string | null; title: string; items: SourceSummary[] }>();
  for (const s of items) {
    const code = s.commission_code ?? null;
    const key = code ?? "~none";
    const g = groups.get(key) ?? { key, code, title: code ? code : "Not filed under a commission yet", items: [] };
    g.items.push(s);
    groups.set(key, g);
  }
  return [...groups.values()].sort((a, b) => (a.code === null ? 1 : b.code === null ? -1 : a.code.localeCompare(b.code)));
}
