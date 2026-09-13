import type { SourceDetail, SourcePageList } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, JobBadge, StageTrack, StateBadge, UnknownBadge } from "../../components";
import { AutoRefresh } from "./auto-refresh";

export const dynamic = "force-dynamic";

export default async function SourceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const detail = await apiTry<SourceDetail>(`/sources/${id}`);
  if (detail.error || !detail.data) {
    return (
      <>
        <h1>Source</h1>
        <ErrorBanner error={detail.error!} />
      </>
    );
  }
  const s = detail.data;
  const pages = s.page_count ? await apiTry<SourcePageList>(`/sources/${id}/pages?limit=1000`) : { data: undefined };
  const job = s.latest_job;
  const noTextRanges = (s.text_layer_summary?.pages_without_text_layer as string[] | undefined) ?? [];
  type LabelSegment = { start_index: number; end_index: number; style: string; offset: number; observed_pages: number };
  const labelSegments = ((s.triage?.label_rule as { segments?: LabelSegment[] } | null | undefined)?.segments ?? []) as LabelSegment[];
  const inFlight = job && (job.status === "queued" || job.status === "leased");
  const done = (job?.progress?.pages_done as number | undefined) ?? 0;
  const total = (job?.progress?.pages_total as number | undefined) ?? s.page_count ?? 0;
  return (
    <>
      {inFlight ? <AutoRefresh seconds={3} /> : null}
      <h1>
        {s.original_filename} <DatasetBadge kind={s.dataset_kind} />
      </h1>
      {s.dataset_kind === "fixture" ? (
        <div className="banner" data-tone="fixture">
          Fixture dataset: synthetic or test material. Never joined with real-utility data.
        </div>
      ) : null}
      <StageTrack state={s.state} />
      {s.state_reason ? (
        <p className="muted">
          Reason: <code>{s.state_reason}</code>
        </p>
      ) : null}
      {job ? (
        <div className="card" aria-live="polite">
          <div className="label">Latest job — {job.job_type}</div>
          <div>
            <JobBadge status={job.status} /> stage <code>{job.stage ?? "—"}</code> · attempt {job.attempts}/{job.max_attempts}
            {job.lease_owner ? (
              <>
                {" "}
                · worker <code>{job.lease_owner}</code>
              </>
            ) : null}
          </div>
          {total > 0 ? (
            <>
              <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
                <div style={{ width: `${Math.round((100 * done) / total)}%` }} />
              </div>
              <div className="muted">
                {done} / {total} pages inventoried
              </div>
            </>
          ) : null}
          {job.error_type ? (
            <div className="banner" data-tone="bad">
              <strong>{job.error_type}</strong> <span className="mono">{job.error_message}</span>
            </div>
          ) : null}
          <div className="muted">
            job <code>{job.id}</code>
            {job.run_id ? (
              <>
                {" "}
                run <code>{job.run_id}</code>
              </>
            ) : null}
          </div>
        </div>
      ) : null}

      <h2>Document</h2>
      <dl className="kv">
        <dt>State</dt>
        <dd>
          <StateBadge state={s.state} />
        </dd>
        <dt>SHA-256</dt>
        <dd className="mono">{s.sha256}</dd>
        <dt>Size</dt>
        <dd>{s.size_bytes.toLocaleString()} bytes</dd>
        <dt>Pages</dt>
        <dd>{s.page_count ?? <UnknownBadge label="pages" />}</dd>
        <dt>Text layer</dt>
        <dd>
          {s.pages_with_text == null ? (
            <UnknownBadge label="text layer" />
          ) : (
            <>
              {s.pages_with_text} pages with text, {s.pages_without_text} without
              {noTextRanges.length ? (
                <>
                  {" "}
                  (no text layer on pages <code>{noTextRanges.join(", ")}</code>)
                </>
              ) : null}
            </>
          )}
        </dd>
        <dt>PDF</dt>
        <dd>
          {s.pdf_version ?? "unknown"} · producer {s.producer ?? "unknown"} · creator {s.creator ?? "unknown"} ·{" "}
          {s.is_encrypted == null ? "encryption unknown" : s.is_encrypted ? "encrypted" : "not encrypted"} ·{" "}
          {s.is_tagged == null ? "tagging unknown" : s.is_tagged ? "tagged" : "not tagged"}
        </dd>
        <dt>Fonts</dt>
        <dd>
          {s.fonts_total == null ? (
            <UnknownBadge label="fonts" />
          ) : s.fonts_not_embedded && s.fonts_not_embedded.length ? (
            <span className="badge" data-tone="warn">
              {s.fonts_not_embedded.length} not embedded: {s.fonts_not_embedded.slice(0, 8).join(", ")}
            </span>
          ) : (
            <>all {s.fonts_total} embedded</>
          )}
        </dd>
        <dt>Inventory tool</dt>
        <dd className="mono">{s.inventory_tool ? `${s.inventory_tool}@${s.inventory_tool_version}` : "not run"}</dd>
        <dt>Provenance</dt>
        <dd>{s.provenance_url ? <a href={s.provenance_url}>{s.provenance_url}</a> : <span className="muted">not recorded</span>}</dd>
        <dt>Uploaded</dt>
        <dd>
          {s.uploaded_by} · {new Date(s.acquired_at).toLocaleString()}
        </dd>
        <dt>Bytes</dt>
        <dd>
          <a href={`/api/sources/${s.id}/file`}>Open the registered PDF (authorized)</a>
        </dd>
        {s.golden_id ? (
          <>
            <dt>Golden manifest</dt>
            <dd>
              <code>{s.golden_id}</code>{" "}
              {s.manifest_check ? (
                <span className="badge" data-tone={s.manifest_check.all_match ? "ok" : "bad"}>
                  {s.manifest_check.all_match ? "matches manifest" : "MISMATCH vs manifest"}
                </span>
              ) : null}
              {s.manifest_check?.checks ? (
                <pre className="mono">{JSON.stringify(s.manifest_check.checks, null, 2)}</pre>
              ) : null}
            </dd>
          </>
        ) : null}
      </dl>

      {s.triage ? (
        <>
          <h2>Triage</h2>
          <p className="muted">
            Rules version <code>{s.triage.triage_version}</code> · {new Date(s.triage.triaged_at!).toLocaleString()}. Every
            class is a deterministic rule with a recorded rationale; <em>unknown</em> means no rule matched and is never
            treated as fine.
          </p>
          <div className="grid">
            {Object.entries(s.triage.page_class_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <div className="card" key={k}>
                  <div className="label">{k}</div>
                  <div className="value">{v}</div>
                </div>
              ))}
          </div>
          <dl className="kv">
            <dt>Needs OCR</dt>
            <dd>
              {s.triage.ocr_recommended_pages.length ? (
                <>
                  <span className="badge" data-tone="warn">{s.triage.ocr_recommended_pages.length} pages</span>{" "}
                  <span className="mono">{s.triage.ocr_recommended_pages.join(", ")}</span>
                  <span className="muted"> — OCR execution is the next increment; these pages are listed, not read</span>
                </>
              ) : (
                "none"
              )}
            </dd>
            <dt>Low text quality</dt>
            <dd>
              {s.triage.low_quality_pages.length ? (
                <span className="mono">{s.triage.low_quality_pages.join(", ")}</span>
              ) : (
                "none"
              )}
            </dd>
            <dt>Unknown class</dt>
            <dd>
              {s.triage.unknown_pages.length ? (
                <>
                  <span className="badge" data-tone="unknown">{s.triage.unknown_pages.length} pages</span>{" "}
                  <span className="mono">{s.triage.unknown_pages.join(", ")}</span>
                </>
              ) : (
                "none"
              )}
            </dd>
            <dt>Printed-label rule</dt>
            <dd>
              {labelSegments.length ? (
                <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
                  {labelSegments.map((seg) => (
                    <li key={seg.start_index}>
                      PDF pages {seg.start_index}–{seg.end_index}: printed label = index {seg.offset >= 0 ? "+" : "−"}{" "}
                      {Math.abs(seg.offset)} ({seg.style.replace("_", " ")}), from {seg.observed_pages} observed footers
                    </li>
                  ))}
                </ul>
              ) : (
                <span className="muted">no printed labels observed — declared PDF labels only, if any</span>
              )}
              {s.triage.label_flagged_pages.length ? (
                <div>
                  <span className="badge" data-tone="warn">label conflict on {s.triage.label_flagged_pages.length} pages</span>{" "}
                  <span className="mono">{s.triage.label_flagged_pages.join(", ")}</span>
                </div>
              ) : null}
            </dd>
            <dt>Artefacts</dt>
            <dd>
              {s.artefacts.filter((a) => a.page_index === 0).map((a) => (
                <div key={a.object_key} className="mono muted">
                  {a.stage} · {a.tool_version} · <code>{a.object_key}</code> · {a.size_bytes} B
                </div>
              ))}
              {s.artefacts.length ? <div className="muted">plus one immutable JSON artefact per page</div> : null}
            </dd>
          </dl>
        </>
      ) : null}

      <h2>Page inventory</h2>
      {!pages.data ? (
        <p className="muted">Not inventoried yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>PDF index</th>
              <th>Printed label</th>
              <th>Size (pt)</th>
              <th>Rotation</th>
              <th>Text chars</th>
              <th>Text layer</th>
              <th>Images</th>
              <th>Drawings</th>
              <th>Class</th>
              <th>Role</th>
            </tr>
          </thead>
          <tbody>
            {pages.data.pages.map((p) => (
              <tr key={p.page_index}>
                <td>{p.page_index}</td>
                <td title={p.triage_rationale ?? undefined}>
                  {p.printed_label ?? <span className="muted">—</span>}{" "}
                  {p.label_source !== "none" ? (
                    <span className="badge" data-tone={p.label_source === "declared" ? "neutral" : "ok"}>{p.label_source}</span>
                  ) : null}
                  {p.quality_flags.some((f) => f === "label_conflict" || f === "label_off_rule") ? (
                    <span className="badge" data-tone="warn">conflict</span>
                  ) : null}
                </td>
                <td className="mono">
                  {p.width_pt?.toFixed(0)}×{p.height_pt?.toFixed(0)}
                </td>
                <td>{p.rotation ? <span className="badge" data-tone="warn">{p.rotation}°</span> : "0°"}</td>
                <td>{p.text_chars}</td>
                <td>
                  {p.has_text_layer ? (
                    <span className="badge" data-tone="ok">present</span>
                  ) : (
                    <span className="badge" data-tone="warn">absent</span>
                  )}
                </td>
                <td>{p.image_count}</td>
                <td>{p.drawing_count}</td>
                <td title={p.triage_rationale ?? "not triaged yet"}>
                  <span className="badge" data-tone={p.page_class === "unknown" ? "unknown" : "neutral"}>{p.page_class}</span>
                  {p.ocr_recommended ? <span className="badge" data-tone="warn">OCR</span> : null}
                  {p.quality_flags.includes("low_text_quality") ? <span className="badge" data-tone="bad">low quality</span> : null}
                </td>
                <td>
                  <span className="badge" data-tone={p.page_role === "unknown" ? "unknown" : "neutral"}>{p.page_role}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
