import Link from "next/link";
import type {
  CandidateList,
  ClauseValueList,
  FindingList,
  LocalisationOut,
  SourceDetail,
  SourcePageList,
  StructureCellList,
} from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner, JobBadge, StageTrack, StateBadge, UnknownBadge } from "../../components";
import { AutoRefresh } from "./auto-refresh";
import { LocalisationForm } from "./localisation-form";

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
  const parse = s.parse; // bound once: TS narrowing does not survive the nested map callbacks below
  const pages = s.page_count ? await apiTry<SourcePageList>(`/sources/${id}/pages?limit=1000`) : { data: undefined };
  const localisation = s.localisation ? await apiTry<LocalisationOut>(`/sources/${id}/localisation`) : { data: undefined };
  const structure = s.structure;
  const unresolvedCells = structure
    ? await apiTry<StructureCellList>(`/sources/${id}/structure/cells?unresolved_only=true&limit=50`)
    : { data: undefined };
  const extraction = s.extraction;
  const validation = s.validation;
  const candidates = extraction
    ? await apiTry<CandidateList>(`/sources/${id}/candidates?limit=100&routing=individual`)
    : { data: undefined };
  const findings = validation ? await apiTry<FindingList>(`/sources/${id}/findings`) : { data: undefined };
  const clauses =
    structure && structure.clause_values > 0
      ? await apiTry<ClauseValueList>(`/sources/${id}/structure/clauses`)
      : { data: undefined };
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

      {parse ? (
        <>
          <h2>Parse — readers, OCR, headings</h2>
          <p className="muted">
            Rules version <code>{parse.parse_version}</code> ·{" "}
            <span className="mono">{String(parse.table_summary?.tool_version ?? "")}</span>. Two independent readers
            reconstruct every table; agreement is a routing signal, never proof. OCR text never replaces a text layer
            silently — where both exist their agreement is measured.
          </p>
          <div className="grid">
            <div className="card">
              <div className="label">Primary table grids</div>
              <div className="value">{String(parse.table_summary?.primary_grids ?? 0)}</div>
            </div>
            {Object.entries((parse.table_summary?.agreement_classes as Record<string, number> | undefined) ?? {}).map(
              ([k, v]) => (
                <div className="card" key={k}>
                  <div className="label">{k.replace(/_/g, " ")}</div>
                  <div className="value">{v}</div>
                </div>
              ),
            )}
            <div className="card">
              <div className="label">OCR pages</div>
              <div className="value">{((parse.table_summary?.ocr_pages as number[] | undefined) ?? []).length}</div>
            </div>
          </div>
          <dl className="kv">
            <dt>Tables needing review</dt>
            <dd>
              {((parse.table_summary?.pages_needing_review as number[] | undefined) ?? []).length ? (
                <>
                  <span className="badge" data-tone="warn">reader disagreement</span>{" "}
                  <span className="mono">pages {((parse.table_summary?.pages_needing_review as number[]) ?? []).join(", ")}</span>
                  <span className="muted"> — both grids are kept; nothing is extracted from these automatically</span>
                </>
              ) : (
                "none"
              )}
            </dd>
            <dt>OCR low confidence</dt>
            <dd>
              {((parse.table_summary?.ocr_low_confidence_pages as number[] | undefined) ?? []).length ? (
                <span className="mono">{((parse.table_summary?.ocr_low_confidence_pages as number[]) ?? []).join(", ")}</span>
              ) : (
                "none"
              )}
            </dd>
            <dt>Grids from OCR</dt>
            <dd>
              {((parse.table_summary?.grid_from_ocr_pending_pages as number[] | undefined) ?? []).length ? (
                <>
                  <span className="badge" data-tone="unknown">not attempted</span>{" "}
                  <span className="mono">pages {((parse.table_summary?.grid_from_ocr_pending_pages as number[]) ?? []).join(", ")}</span>
                  <span className="muted"> — table reconstruction from OCR word boxes is not built yet; these pages are listed for review</span>
                </>
              ) : (
                "none needed"
              )}
            </dd>
            <dt>Heading inventory</dt>
            <dd>
              {Object.entries((parse.heading_inventory?.counts as Record<string, number> | undefined) ?? {}).map(([k, v]) => (
                <div key={k}>
                  <strong>{k.replace(/_/g, " ")}</strong>: {v}{" "}
                  <span className="mono muted">
                    {(((parse.heading_inventory?.unique_codes as Record<string, string[]>) ?? {})[k] ?? []).join(", ")}
                  </span>
                  {(((parse.heading_inventory?.repeated_codes as Record<string, string[]>) ?? {})[k] ?? []).length ? (
                    <span className="badge" data-tone="warn">
                      repeated: {(((parse.heading_inventory?.repeated_codes as Record<string, string[]>) ?? {})[k] ?? []).join(", ")}
                    </span>
                  ) : null}
                </div>
              ))}
              {Object.keys((parse.heading_inventory?.counts as Record<string, number> | undefined) ?? {}).length === 0 ? (
                <span className="muted">no schedule, annexure, chapter or table headings recognised</span>
              ) : null}
            </dd>
          </dl>
        </>
      ) : null}

      <h2>Localisation checkpoint</h2>
      <p className="muted">
        Reading profile:{" "}
        {s.reading_profile.profile_id ? (
          <>
            <code>
              {s.reading_profile.profile_id}@{s.reading_profile.version}
            </code>{" "}
            ({s.reading_profile.source}: {s.reading_profile.rationale})
          </>
        ) : (
          <UnknownBadge label="none yet" />
        )}
      </p>
      {!localisation.data ? (
        <p className="muted">Not localised yet: the stage runs after parsing.</p>
      ) : (
        <>
          <div
            className="banner"
            data-tone={
              localisation.data.status === "ambiguous"
                ? "bad"
                : localisation.data.extraction_allowed
                  ? "ok"
                  : "warn"
            }
          >
            {localisation.data.status === "ambiguous"
              ? "Halted: the rules could not localise the approved schedule unambiguously. A reviewer must correct the regions."
              : localisation.data.extraction_allowed
                ? `Localisation ${localisation.data.status} by ${localisation.data.decided_by}. Extraction may proceed.`
                : "Proposed by the rules. A reviewer must confirm the page ranges before any extraction (mandatory checkpoint)."}
            {" "}
            <span className="mono muted">rules {localisation.data.rules_version} · profile {localisation.data.profile_ref}</span>
          </div>
          {localisation.data.findings.length ? (
            <ul>
              {localisation.data.findings.map((f, i) => (
                <li key={i}>
                  <span className="badge" data-tone={f.severity === "blocking" ? "bad" : f.severity === "warning" ? "warn" : "neutral"}>
                    {f.severity}
                  </span>{" "}
                  <code>{f.code}</code> {f.message}
                  {(f.pages ?? []).length ? <span className="mono muted"> pages {(f.pages ?? []).join(", ")}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Role</th>
                  <th>Pages</th>
                  <th>Cue</th>
                  <th>Utility / period</th>
                  <th>Grids</th>
                  <th>Origin</th>
                </tr>
              </thead>
              <tbody>
                {localisation.data.regions.map((r) => (
                  <tr key={r.id} data-role={r.role}>
                    <td>
                      <strong>{r.role.replace(/_/g, " ")}</strong>
                      {r.sub_role ? <span className="muted"> / {r.sub_role.replace(/_/g, " ")}</span> : null}
                    </td>
                    <td className="mono">
                      {r.page_start === r.page_end ? r.page_start : `${r.page_start}–${r.page_end}`}
                    </td>
                    <td>
                      <code>{r.cue_text}</code>
                      <span className="muted"> (p. {r.cue_page}, {r.cue_kind})</span>
                      {r.note ? <div className="muted">{r.note}</div> : null}
                    </td>
                    <td>{[r.utility, r.period].filter(Boolean).join(" · ") || "—"}</td>
                    <td className="mono">{r.grid_count}</td>
                    <td>{r.origin}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!localisation.data.extraction_allowed ? (
            <LocalisationForm sourceId={id} record={localisation.data} />
          ) : (
            <p className="muted">
              Decided by {localisation.data.decided_by} · decisions {localisation.data.decision_count} · rationale:{" "}
              <em>{localisation.data.decision_rationale}</em>
            </p>
          )}
        </>
      )}

      <h2>Structure integrity</h2>
      {!structure ? (
        <p className="muted">
          Not built yet: the structure stage runs only after a reviewer confirms the localisation (Section 6.6).
        </p>
      ) : (
        <>
          <p className="muted">
            <span className="mono">{structure.tool_version}</span> · representation {structure.representation} · regions read{" "}
            {structure.regions_read}, skipped {structure.regions_skipped}
            {structure.regions_without_grids.length ? (
              <>
                {" "}
                · <span className="badge" data-tone="warn">no grids in region {structure.regions_without_grids.join(", ")}</span>
              </>
            ) : null}
          </p>
          <div className="stats">
            <div className="stat">
              <div className="label">Numeric cells</div>
              <div className="value">{structure.cells}</div>
            </div>
            <div className="stat">
              <div className="label">Resolved (header + row + unit)</div>
              <div className="value">{structure.cells_resolved}</div>
            </div>
            <div className="stat">
              <div className="label">Unresolved, listed</div>
              <div className="value">{structure.cells_unresolved}</div>
            </div>
            <div className="stat">
              <div className="label">Continuations / inherited headers</div>
              <div className="value">
                {structure.continuations} / {structure.header_inherited_grids}
              </div>
            </div>
            <div className="stat">
              <div className="label">Clause values</div>
              <div className="value">{structure.clause_values}</div>
            </div>
          </div>
          <p className="muted">
            Unit sources:{" "}
            {Object.entries(structure.unit_sources)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ") || "—"}
            {" · "}flags:{" "}
            {Object.entries(structure.flags)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ") || "none"}
          </p>
          {unresolvedCells.data && unresolvedCells.data.total > 0 ? (
            <div className="table-wrap">
              <table>
                <caption>Cells that resolve to no header path, row path or unit ({unresolvedCells.data.total}); never defaulted</caption>
                <thead>
                  <tr>
                    <th>Page</th>
                    <th>Grid / cell</th>
                    <th>Text</th>
                    <th>Header path</th>
                    <th>Row path</th>
                    <th>Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {unresolvedCells.data.cells.map((c) => (
                    <tr key={c.id}>
                      <td className="mono">{c.page_index}</td>
                      <td className="mono">
                        {c.grid_ordinal} · r{c.row} c{c.col}
                      </td>
                      <td>
                        <code>{c.raw}</code>
                      </td>
                      <td>{c.header_path.join(" > ") || "—"}</td>
                      <td>{c.row_path.join(" > ") || "—"}</td>
                      <td className="mono">{c.flags.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {clauses.data ? (
            <div className="table-wrap">
              <table>
                <caption>Clause outline ({clauses.data.total} lines)</caption>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Clause path</th>
                    <th>Role</th>
                    <th>Value</th>
                    <th>Unit</th>
                    <th>Dimension / slab / window</th>
                  </tr>
                </thead>
                <tbody>
                  {clauses.data.values.map((v) => (
                    <tr key={v.id}>
                      <td className="mono">
                        {v.category_code}
                        {v.alternative ? <span className="muted"> alt {v.alternative + 1}</span> : null}
                        {v.connector ? <span className="muted"> {v.connector}</span> : null}
                      </td>
                      <td>{v.clause_path.slice(1).join(" > ")}</td>
                      <td>
                        {v.role}
                        {v.kind !== "value" ? <span className="badge" data-tone="warn">{v.kind}</span> : null}
                      </td>
                      <td className="mono">
                        {v.value ?? v.reference ?? "—"}
                        {v.sign ? (v.sign > 0 ? " (+)" : " (−)") : ""}
                        {v.percent_of ? <span className="muted"> % of {v.percent_of}</span> : null}
                      </td>
                      <td className="mono">{[v.currency, v.per_unit, v.frequency].filter(Boolean).join(" / ") || "—"}</td>
                      <td className="muted">
                        {v.dimension ? `${v.dimension.metering_type}` : ""}
                        {v.slab ? ` slab ${v.slab.lower ?? ""}–${v.slab.upper ?? ""} (${v.slab.inclusivity})` : ""}
                        {v.time_window ? ` ${v.time_window}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}

      <h2>Candidates and validation</h2>
      {s.state === "awaiting_review" ? (
        <p>
          <Link href={`/sources/${id}/review`}>Open the review workspace</Link> — side-by-side evidence, decisions with rationale,
          completeness checklist.
        </p>
      ) : null}
      {!extraction ? (
        <p className="muted">Not extracted yet: extraction runs after the structure stage, from confirmed regions only.</p>
      ) : (
        <>
          <div className="banner" data-tone={extraction.is_fixture ? "fixture" : "neutral"}>
            {extraction.is_fixture ? "Fixture provider run — labelled, never mixed with real runs." : `Real provider run: ${extraction.provider} ${extraction.model}.`}{" "}
            <span className="mono muted">
              prompt {extraction.prompt_version} · schema {extraction.schema_version} · {extraction.runs} runs · {extraction.tokens} tokens ·{" "}
              {extraction.cost_usd} USD
            </span>
          </div>
          <div className="stats">
            <div className="stat">
              <div className="label">Candidates</div>
              <div className="value">{extraction.candidates}</div>
            </div>
            <div className="stat">
              <div className="label">Channel agreement</div>
              <div className="value">
                {Object.entries(extraction.by_agreement)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(" · ")}
              </div>
            </div>
            <div className="stat">
              <div className="label">Confidence</div>
              <div className="value">
                {Object.entries(extraction.by_confidence)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(" · ")}
              </div>
            </div>
            <div className="stat">
              <div className="label">Routing</div>
              <div className="value">
                {Object.entries(extraction.by_routing)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(" · ")}
              </div>
            </div>
            {validation ? (
              <div className="stat">
                <div className="label">Validator findings</div>
                <div className="value">
                  {validation.findings}{" "}
                  <span className="muted">
                    ({Object.entries(validation.by_severity)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(" · ")})
                  </span>
                </div>
              </div>
            ) : null}
          </div>
          <p className="muted">
            Risk tags:{" "}
            {Object.entries(extraction.risk_tags)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ") || "none"}
            {extraction.new_profile ? " · first order read with this profile: everything is individual review" : ""}
          </p>
          {validation && validation.families_without_disposition.length ? (
            <div className="banner" data-tone="warn">
              Charge families with no candidate, no decision status and no reviewed disposition:{" "}
              <span className="mono">{validation.families_without_disposition.join(", ")}</span>. Coverage cannot be declared complete
              until a reviewer records what this order decides for each.
            </div>
          ) : null}
          {findings.data && findings.data.total > 0 ? (
            <div className="table-wrap">
              <table>
                <caption>Validator findings ({findings.data.total})</caption>
                <thead>
                  <tr>
                    <th>Validator</th>
                    <th>Severity</th>
                    <th>Finding</th>
                    <th>Candidates</th>
                  </tr>
                </thead>
                <tbody>
                  {findings.data.findings.map((f) => (
                    <tr key={f.id}>
                      <td className="mono">{f.validator_id}</td>
                      <td>
                        <span className="badge" data-tone={f.severity === "blocking" ? "bad" : f.severity === "warning" ? "warn" : "neutral"}>
                          {f.severity}
                        </span>
                      </td>
                      <td>{f.message}</td>
                      <td className="mono">{f.candidate_ids.length || "source"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {candidates.data ? (
            <div className="table-wrap">
              <table>
                <caption>
                  Candidates for individual review ({candidates.data.total}; first {candidates.data.candidates.length}) — proposals, not facts
                </caption>
                <thead>
                  <tr>
                    <th>Family / category</th>
                    <th>Component</th>
                    <th>Value</th>
                    <th>State</th>
                    <th>Unit</th>
                    <th>Applies to</th>
                    <th>Evidence</th>
                    <th>Confidence / risks</th>
                    <th>Channels</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.data.candidates.map((c) => {
                    const rec = c.record as {
                      applicability?: { description?: string | null; time_band?: string | null; metering_type?: string | null; slab?: { original_text?: string | null } | null; load_band?: { original_text?: string | null } | null; alternative?: number | null };
                      evidence?: { page_index: number; kind: string; row?: number | null; col?: number | null; line_no?: number | null }[];
                      sign?: number | null;
                      reference_target?: string | null;
                    };
                    const a = rec.applicability ?? {};
                    const ev = rec.evidence?.[0];
                    return (
                      <tr key={c.id}>
                        <td>
                          <span className="mono">{c.family}</span>
                          {c.category_code ? <div className="mono">{c.category_code}</div> : null}
                        </td>
                        <td>{c.component_type}</td>
                        <td className="mono">
                          {c.value ?? rec.reference_target ?? "—"}
                          {rec.sign ? (rec.sign > 0 ? " (+)" : " (−)") : ""}
                        </td>
                        <td>
                          <code>{c.value_state}</code>
                          {c.decision_status ? <div className="muted">{c.decision_status}</div> : null}
                        </td>
                        <td className="mono">{[c.currency, c.per_unit, c.frequency].filter(Boolean).join(" / ") || "—"}</td>
                        <td className="muted">
                          {[a.description, a.slab?.original_text ?? a.load_band?.original_text, a.time_band, a.metering_type, a.alternative != null ? `alt ${a.alternative + 1}` : null]
                            .filter(Boolean)
                            .join(" · ")}
                        </td>
                        <td className="mono">
                          {ev ? `p${ev.page_index} ${ev.kind}${ev.row != null ? ` r${ev.row} c${ev.col}` : ev.line_no != null ? ` l${ev.line_no}` : ""}` : "—"}
                        </td>
                        <td>
                          <span className="badge" data-tone={c.confidence === "high" ? "ok" : c.confidence === "medium" ? "warn" : "bad"}>
                            {c.confidence}
                          </span>{" "}
                          <span className="mono muted">{c.risk_tags.join(", ")}</span>
                        </td>
                        <td>
                          <span className="badge" data-tone={c.channel_agreement === "agree" ? "ok" : c.channel_agreement === "disagree" ? "bad" : "warn"}>
                            {c.channel_agreement}
                          </span>
                          {c.disagreeing_fields.length ? <span className="mono muted"> {c.disagreeing_fields.join(", ")}</span> : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}

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
                  {p.ocr_used ? (
                    <span className="badge" data-tone={p.quality_flags.includes("ocr_low_confidence") ? "bad" : "ok"}>
                      OCR {p.ocr_confidence != null ? `${Math.round(p.ocr_confidence)}%` : ""}
                    </span>
                  ) : null}
                  {p.quality_flags.includes("structure_disagreement") || p.quality_flags.includes("empty_grid") ? (
                    <span className="badge" data-tone="warn">readers disagree</span>
                  ) : null}
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
