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
import { RegionNote } from "./region-note";
import { PageList, Section, Stat, ranges } from "./ui";

export const dynamic = "force-dynamic";

const num = (v: unknown): number[] => (Array.isArray(v) ? (v as number[]) : []);
const rec = (v: unknown): Record<string, number> => (v && typeof v === "object" ? (v as Record<string, number>) : {});
const fmt = (o: Record<string, number>) =>
  Object.entries(o)
    .map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`)
    .join(" · ");

export default async function SourceDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const allPages = sp.pages === "all";
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
  const parse = s.parse;
  const structure = s.structure;
  const extraction = s.extraction;
  const validation = s.validation;
  const [pages, localisation, unresolvedCells, candidates, findings, clauses] = await Promise.all([
    s.page_count ? apiTry<SourcePageList>(`/sources/${id}/pages?limit=1000`) : Promise.resolve({ data: undefined }),
    s.localisation ? apiTry<LocalisationOut>(`/sources/${id}/localisation`) : Promise.resolve({ data: undefined }),
    structure ? apiTry<StructureCellList>(`/sources/${id}/structure/cells?unresolved_only=true&limit=50`) : Promise.resolve({ data: undefined }),
    extraction ? apiTry<CandidateList>(`/sources/${id}/candidates?limit=100&routing=individual`) : Promise.resolve({ data: undefined }),
    validation ? apiTry<FindingList>(`/sources/${id}/findings`) : Promise.resolve({ data: undefined }),
    structure && structure.clause_values > 0 ? apiTry<ClauseValueList>(`/sources/${id}/structure/clauses`) : Promise.resolve({ data: undefined }),
  ]);
  const job = s.latest_job;
  const inFlight = !!job && (job.status === "queued" || job.status === "leased");
  const done = (job?.progress?.pages_done as number | undefined) ?? 0;
  const total = (job?.progress?.pages_total as number | undefined) ?? s.page_count ?? 0;
  const loc = localisation.data;
  const checkpointOpen = !!loc && !loc.extraction_allowed;
  const reviewable = s.state === "awaiting_review" || s.state === "published";
  const regionsEditable = s.state === "localised" || s.state === "gridded";
  type LabelSegment = { start_index: number; end_index: number; style: string; offset: number; observed_pages: number };
  const labelSegments = ((s.triage?.label_rule as { segments?: LabelSegment[] } | null | undefined)?.segments ?? []) as LabelSegment[];
  const ts = parse?.table_summary as Record<string, unknown> | undefined;
  const hi = parse?.heading_inventory as Record<string, unknown> | undefined;
  const headingCounts = rec(hi?.counts);
  const headingCodes = (hi?.unique_codes as Record<string, string[]> | undefined) ?? {};
  const headingRepeated = (hi?.repeated_codes as Record<string, string[]> | undefined) ?? {};

  // Page roles come from the localisation regions (the page table's own role column is
  // never assigned by any stage); a page can sit in several regions.
  const rolesByPage = new Map<number, string[]>();
  for (const r of loc?.regions ?? []) {
    for (let p = r.page_start; p <= r.page_end; p++) {
      const label = r.sub_role ? `${r.role}/${r.sub_role}` : r.role;
      rolesByPage.set(p, [...(rolesByPage.get(p) ?? []), label]);
    }
  }
  const flagged = (p: SourcePageList["pages"][number]) =>
    p.ocr_recommended || p.page_class === "unknown" || p.quality_flags.length > 0 || !p.has_text_layer || !!p.rotation;
  const pageRows = pages.data ? (allPages ? pages.data.pages : pages.data.pages.filter(flagged)) : [];
  const flaggedCount = pages.data ? pages.data.pages.filter(flagged).length : 0;

  // The one thing the reader needs first: what happens next, and whether it is theirs to do.
  let action: { tone: string; title: string; body: React.ReactNode };
  if (job?.status === "failed") {
    action = {
      tone: "bad",
      title: `The ${job.job_type.replace(/_/g, " ")} job failed`,
      body: (
        <>
          <code>{job.error_type}</code> {job.error_message} — see <Link href="/jobs">Jobs</Link>.
        </>
      ),
    };
  } else if (inFlight) {
    action = {
      tone: "neutral",
      title: `Processing: ${job!.job_type.replace(/_/g, " ")} is ${job!.status}`,
      body: total > 0 ? `${done} / ${total} pages. This page refreshes itself.` : "This page refreshes itself.",
    };
  } else if (checkpointOpen) {
    action = {
      tone: loc!.status === "ambiguous" ? "bad" : "warn",
      title: loc!.status === "ambiguous" ? "Your action: correct the localisation" : "Your action: confirm or correct the localisation",
      body: (
        <>
          {loc!.status === "ambiguous"
            ? "The rules could not find the approved schedule unambiguously. "
            : "The rules proposed the page ranges below. "}
          Open the PDF at the boundary pages, then decide in the <a href="#checkpoint">checkpoint section</a>. Nothing is
          extracted until you do.
        </>
      ),
    };
  } else if (s.state === "localised") {
    action = {
      tone: "ok",
      title: `Localisation ${loc?.status ?? "decided"} by ${loc?.decided_by ?? "a reviewer"}`,
      body: "The structure, extraction and validation stages run on the next worker run (make drain-dev).",
    };
  } else if (s.state === "awaiting_review") {
    action = {
      tone: "warn",
      title: `Your action: review ${extraction?.candidates ?? ""} candidates`,
      body: (
        <>
          <Link href={`/sources/${id}/review`}>Open the review workspace</Link> — every value is a proposal until a reviewer
          decides. <Link href={`/sources/${id}/publish`}>Publish a release</Link> once the checklist allows.
        </>
      ),
    };
  } else if (s.state === "published" && s.publication) {
    action = {
      tone: "ok",
      title: `Published: release ${s.publication.release_number} (${s.publication.completeness}), ${s.publication.fact_count} facts`,
      body: (
        <>
          <Link href={`/explorer/${id}`}>Open in the explorer</Link> · <Link href={`/sources/${id}/review`}>Review workspace</Link>{" "}
          · <Link href={`/sources/${id}/publish`}>Publish again</Link>
          {s.publication.is_fixture ? " · FIXTURE release, never coverage" : ""}
        </>
      ),
    };
  } else if (["failed", "cancelled", "rejected", "superseded", "needs_reprocessing"].includes(s.state)) {
    action = { tone: "bad", title: `Source is ${s.state.replace(/_/g, " ")}`, body: s.state_reason ?? "" };
  } else {
    action = {
      tone: "neutral",
      title: `In the pipeline: ${s.state.replace(/_/g, " ")}`,
      body: "The next stage runs on the next worker run. No reviewer action is needed yet.",
    };
  }

  return (
    <>
      {inFlight ? <AutoRefresh seconds={3} /> : null}
      <p className="muted crumbs">
        <Link href="/sources">Source inbox</Link> › {s.original_filename}
      </p>
      <h1>
        {s.original_filename} <DatasetBadge kind={s.dataset_kind} /> <StateBadge state={s.state} />
      </h1>
      {s.dataset_kind === "fixture" ? (
        <div className="banner" data-tone="fixture">
          Fixture dataset: synthetic or test material. Never joined with real-utility data.
        </div>
      ) : null}
      <div className="banner action" data-tone={action.tone} role="status">
        <strong>{action.title}</strong>
        <div>{action.body}</div>
      </div>
      <StageTrack state={s.state} />
      <div className="facts muted">
        {s.page_count != null ? `${s.page_count} pages` : "pages unknown"}
        {s.pages_without_text ? ` · ${s.pages_without_text} without a text layer` : ""}
        {s.triage ? ` · triage rules ${s.triage.triage_version}` : ""}
        {parse ? ` · parse rules ${parse.parse_version}` : ""}
        {s.reading_profile.profile_id ? ` · profile ${s.reading_profile.profile_id}@${s.reading_profile.version}` : ""}
        {s.golden_id && s.manifest_check ? ` · manifest ${s.manifest_check.all_match ? "matches" : "MISMATCH"}` : ""}
        {job ? (
          <>
            {" "}
            · last job {job.job_type.replace(/_/g, " ")} <JobBadge status={job.status} />
          </>
        ) : null}
      </div>

      <Section
        id="checkpoint"
        title="Localisation checkpoint"
        open={checkpointOpen || s.state === "localised"}
        summary={
          !loc
            ? "not localised yet"
            : loc.extraction_allowed
              ? `${loc.status} by ${loc.decided_by} · ${loc.regions.length} regions`
              : `${loc.regions.length} regions proposed · awaiting a reviewer`
        }
      >
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
          {loc ? (
            <>
              {" "}
              · rules {loc.rules_version} · profile {loc.profile_ref}
            </>
          ) : null}
        </p>
        {!loc ? (
          <p className="muted">Not localised yet: the stage runs after parsing.</p>
        ) : (
          <>
            {loc.findings.length ? (
              <ul className="findings">
                {loc.findings.map((f, i) => (
                  <li key={i}>
                    <span className="badge" data-tone={f.severity === "blocking" ? "bad" : f.severity === "warning" ? "warn" : "neutral"}>
                      {f.severity}
                    </span>{" "}
                    {f.message}
                    {(f.pages ?? []).length ? <span className="mono muted"> pages {ranges(f.pages ?? [])}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {!loc.extraction_allowed ? (
              <LocalisationForm sourceId={id} record={loc} />
            ) : (
              <p className="muted">
                Decided by {loc.decided_by} · decisions {loc.decision_count} · rationale: <em>{loc.decision_rationale}</em>
              </p>
            )}
            <div className="table-wrap">
              <table className="compact">
                <caption>
                  Regions the rules found, grouped by role. Only the approved schedule and the network-charge regions feed
                  extraction. Comment on any region; exclude one to keep the stages off it (the note follows the family into
                  the review checklist).
                </caption>
                <thead>
                  <tr>
                    <th>Role</th>
                    <th>Pages</th>
                    <th>Cue found on the page</th>
                    <th>Utility / period</th>
                    <th>Grids</th>
                    <th>Reviewer comment</th>
                  </tr>
                </thead>
                <tbody>
                  {[...loc.regions]
                    .sort((a, b) => a.role.localeCompare(b.role) || a.page_start - b.page_start)
                    .map((r, i, arr) => (
                      <tr
                        key={r.id}
                        data-role={r.role}
                        data-excluded={r.excluded || undefined}
                        className={i > 0 && arr[i - 1].role !== r.role ? "group-start" : undefined}
                      >
                        <td>
                          {i === 0 || arr[i - 1].role !== r.role ? <strong>{r.role.replace(/_/g, " ")}</strong> : null}
                          {r.sub_role ? <div className="muted">{r.sub_role.replace(/_/g, " ")}</div> : null}
                        </td>
                        <td className="mono">{r.page_start === r.page_end ? r.page_start : `${r.page_start}–${r.page_end}`}</td>
                        <td>
                          <span className="cue">{r.cue_text}</span>
                          <span className="muted"> (p. {r.cue_page})</span>
                          {r.origin !== "detected" ? <span className="badge" data-tone="ok"> {r.origin}</span> : null}
                        </td>
                        <td className="muted">{[r.utility, r.period].filter(Boolean).join(" · ") || "—"}</td>
                        <td className="mono">{r.grid_count}</td>
                        <td>
                          <RegionNote sourceId={id} region={r} version={loc.version} editable={regionsEditable} />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Section>

      <Section
        id="candidates"
        title="Candidates and validation"
        open={reviewable}
        summary={
          !extraction
            ? "not extracted yet"
            : `${extraction.candidates} candidates · ${validation ? `${validation.findings} findings` : "not validated"}${extraction.is_fixture ? " · fixture provider" : ""}`
        }
      >
        {reviewable ? (
          <p>
            <Link href={`/sources/${id}/review`}>Open the review workspace</Link> — side-by-side evidence, decisions with rationale,
            completeness checklist. <Link href={`/sources/${id}/publish`}>Publish a release</Link> — declared scope, completeness
            declaration, consequences shown first.
          </p>
        ) : null}
        {s.publication ? (
          <div className="banner" data-tone={s.publication.completeness === "complete" ? "ok" : "warn"}>
            Release {s.publication.release_number} ({s.publication.completeness}
            {s.publication.completeness === "partial" ? `, ${s.publication.gaps.length} declared gap(s)` : ""}) · {s.publication.fact_count}{" "}
            published facts · by {s.publication.published_by}. <Link href={`/explorer/${id}`}>Open in the explorer</Link>
            {s.publication.is_fixture ? " · FIXTURE release, never coverage" : ""}
          </div>
        ) : null}
        {!extraction ? (
          <p className="muted">Not extracted yet: extraction runs after the structure stage, from confirmed regions only.</p>
        ) : (
          <>
            <div className="banner" data-tone={extraction.is_fixture ? "fixture" : "neutral"}>
              {extraction.is_fixture
                ? "Fixture provider run — deterministic rules over the document's own cells, labelled, never mixed with real runs."
                : `Real provider run: ${extraction.provider} ${extraction.model}.`}{" "}
              <span className="mono muted">
                prompt {extraction.prompt_version} · schema {extraction.schema_version} · {extraction.runs} runs · {extraction.tokens} tokens ·{" "}
                {extraction.cost_usd} USD
              </span>
            </div>
            <div className="stats">
              <Stat label="Candidates" value={extraction.candidates} />
              <Stat label="Channel agreement" value={fmt(extraction.by_agreement)} />
              <Stat label="Confidence" value={fmt(extraction.by_confidence)} />
              <Stat label="Routing" value={fmt(extraction.by_routing)} />
              {validation ? <Stat label="Validator findings" value={`${validation.findings} (${fmt(validation.by_severity)})`} /> : null}
            </div>
            <p className="muted">
              Risk tags: {fmt(extraction.risk_tags) || "none"}
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
              <details className="inline">
                <summary>Validator findings ({findings.data.total})</summary>
                <div className="table-wrap">
                  <table className="compact">
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
              </details>
            ) : null}
            {candidates.data ? (
              <div className="table-wrap">
                <table className="compact">
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
                      const r = c.record as {
                        applicability?: {
                          description?: string | null;
                          time_band?: string | null;
                          metering_type?: string | null;
                          slab?: { original_text?: string | null } | null;
                          load_band?: { original_text?: string | null } | null;
                          alternative?: number | null;
                        };
                        evidence?: { page_index: number; kind: string; row?: number | null; col?: number | null; line_no?: number | null }[];
                        sign?: number | null;
                        reference_target?: string | null;
                      };
                      const a = r.applicability ?? {};
                      const ev = r.evidence?.[0];
                      return (
                        <tr key={c.id}>
                          <td>
                            <span className="mono">{c.family}</span>
                            {c.category_code ? <div className="mono">{c.category_code}</div> : null}
                          </td>
                          <td>{c.component_type}</td>
                          <td className="mono">
                            {c.value ?? r.reference_target ?? "—"}
                            {r.sign ? (r.sign > 0 ? " (+)" : " (−)") : ""}
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
      </Section>

      <Section
        id="structure"
        title="Structure integrity"
        open={!!structure && structure.cells_unresolved > 0 && !reviewable}
        summary={
          !structure
            ? "not built yet"
            : `${structure.cells} numeric cells · ${structure.cells_resolved} resolved · ${structure.cells_unresolved} unresolved · ${structure.clause_values} clause values`
        }
      >
        {!structure ? (
          <p className="muted">Not built yet: the structure stage runs only after a reviewer confirms the localisation.</p>
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
              {" · "}unit sources: {fmt(structure.unit_sources) || "—"} · flags: {fmt(structure.flags) || "none"}
            </p>
            <div className="stats">
              <Stat label="Numeric cells" value={structure.cells} />
              <Stat label="Resolved (header + row + unit)" value={structure.cells_resolved} />
              <Stat label="Unresolved, listed" value={structure.cells_unresolved} tone={structure.cells_unresolved ? "warn" : undefined} />
              <Stat label="Continuations / inherited headers" value={`${structure.continuations} / ${structure.header_inherited_grids}`} />
              <Stat label="Clause values" value={structure.clause_values} />
            </div>
            {unresolvedCells.data && unresolvedCells.data.total > 0 ? (
              <details className="inline">
                <summary>Cells that resolve to no header path, row path or unit ({unresolvedCells.data.total}); never defaulted</summary>
                <div className="table-wrap">
                  <table className="compact">
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
              </details>
            ) : null}
            {clauses.data ? (
              <details className="inline">
                <summary>Clause outline ({clauses.data.total} lines)</summary>
                <div className="table-wrap">
                  <table className="compact">
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
              </details>
            ) : null}
          </>
        )}
      </Section>

      <Section
        id="parse"
        title="Parse: readers, OCR, headings"
        summary={
          !parse
            ? "not parsed yet"
            : `${String(ts?.primary_grids ?? 0)} table grids · ${num(ts?.pages_needing_review).length} pages with reader disagreement · ${num(ts?.ocr_pages).length} OCR pages · ${Object.entries(headingCounts).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")}`
        }
      >
        {!parse ? (
          <p className="muted">Not parsed yet: the stage runs after triage.</p>
        ) : (
          <>
            <p className="muted">
              Rules {parse.parse_version} · <span className="mono">{String(ts?.tool_version ?? "")}</span>. Two independent readers
              reconstruct every table; agreement is a routing signal, never proof. OCR text never replaces a text layer silently.
            </p>
            <div className="stats">
              <Stat label="Primary table grids" value={String(ts?.primary_grids ?? 0)} />
              {Object.entries(rec(ts?.agreement_classes)).map(([k, v]) => (
                <Stat key={k} label={k.replace(/_/g, " ")} value={v} tone={k.includes("disagreement") && v > 0 ? "warn" : undefined} />
              ))}
              <Stat label="OCR pages" value={num(ts?.ocr_pages).length} />
            </div>
            <dl className="kv">
              <dt>Reader disagreement</dt>
              <dd>
                <PageList pages={num(ts?.pages_needing_review)} label="pages" />
                <span className="muted"> — both grids are kept; nothing is extracted from these automatically</span>
              </dd>
              <dt>OCR low confidence</dt>
              <dd>
                <PageList pages={num(ts?.ocr_low_confidence_pages)} label="pages" tone="bad" />
              </dd>
              <dt>Grids from OCR</dt>
              <dd>
                {num(ts?.grid_from_ocr_pending_pages).length ? (
                  <>
                    <PageList pages={num(ts?.grid_from_ocr_pending_pages)} label="pages not attempted" tone="unknown" />
                    <span className="muted"> — table reconstruction from OCR word boxes is not built yet</span>
                  </>
                ) : (
                  "none needed"
                )}
              </dd>
              <dt>Headings</dt>
              <dd>
                {Object.keys(headingCounts).length === 0 ? (
                  <span className="muted">no schedule, annexure, chapter or table headings recognised</span>
                ) : (
                  Object.entries(headingCounts).map(([k, v]) => {
                    const codes = headingCodes[k] ?? [];
                    const rep = headingRepeated[k] ?? [];
                    const body = (
                      <>
                        <span className="mono">{codes.join(", ")}</span>
                        {rep.length ? (
                          <div>
                            <span className="badge" data-tone="warn">repeated</span> <span className="mono muted">{rep.join(", ")}</span>
                          </div>
                        ) : null}
                      </>
                    );
                    return (
                      <div key={k}>
                        <strong>{k.replace(/_/g, " ")}</strong>: {v}{" "}
                        {codes.length > 20 ? (
                          <details className="inline">
                            <summary className="muted">show codes</summary>
                            {body}
                          </details>
                        ) : (
                          body
                        )}
                      </div>
                    );
                  })
                )}
              </dd>
            </dl>
          </>
        )}
      </Section>

      <Section
        id="triage"
        title="Triage: page classes and printed labels"
        summary={
          !s.triage
            ? "not triaged yet"
            : `${fmt(s.triage.page_class_counts)} · ${s.triage.ocr_recommended_pages.length} pages OCR · ${s.triage.label_flagged_pages.length} label conflicts`
        }
      >
        {!s.triage ? (
          <p className="muted">Not triaged yet: the stage runs after inventory.</p>
        ) : (
          <>
            <p className="muted">
              Rules {s.triage.triage_version} · {new Date(s.triage.triaged_at!).toLocaleString()}. Every class is a deterministic rule with a
              recorded rationale; <em>unknown</em> means no rule matched and is never treated as fine.
            </p>
            <div className="stats">
              {Object.entries(s.triage.page_class_counts)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <Stat key={k} label={k.replace(/_/g, " ")} value={v} tone={k === "unknown" ? "unknown" : undefined} />
                ))}
            </div>
            <dl className="kv">
              <dt>OCR</dt>
              <dd>
                <PageList pages={s.triage.ocr_recommended_pages} label="pages" />
                <span className="muted"> — OCR ran on these in the parse stage; words carry per-word confidence</span>
              </dd>
              <dt>Low text quality</dt>
              <dd>
                <PageList pages={s.triage.low_quality_pages} label="pages" tone="bad" />
              </dd>
              <dt>Unknown class</dt>
              <dd>
                <PageList pages={s.triage.unknown_pages} label="pages" tone="unknown" />
              </dd>
              <dt>Printed labels</dt>
              <dd>
                {labelSegments.length ? (
                  labelSegments.map((seg) => (
                    <div key={seg.start_index}>
                      PDF pages {seg.start_index}–{seg.end_index}: printed label = index {seg.offset >= 0 ? "+" : "−"} {Math.abs(seg.offset)} (
                      {seg.style.replace("_", " ")}), from {seg.observed_pages} observed footers
                    </div>
                  ))
                ) : (
                  <span className="muted">no printed labels observed — declared PDF labels only, if any</span>
                )}
                {s.triage.label_flagged_pages.length ? (
                  <div>
                    <PageList pages={s.triage.label_flagged_pages} label="pages where the footer disagrees with the rule" />
                    <span className="muted"> — usually a table number read as a page label; the rule stands</span>
                  </div>
                ) : null}
              </dd>
            </dl>
          </>
        )}
      </Section>

      <Section
        id="document"
        title="Document"
        summary={`${s.size_bytes.toLocaleString()} bytes · ${s.pdf_version ?? "PDF"} · ${s.producer ?? "producer unknown"} · uploaded ${new Date(s.acquired_at).toLocaleDateString()}`}
      >
        <dl className="kv">
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
                {((s.text_layer_summary?.pages_without_text_layer as string[] | undefined) ?? []).length ? (
                  <>
                    {" "}
                    (<code>{((s.text_layer_summary?.pages_without_text_layer as string[]) ?? []).join(", ")}</code>)
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
                  <div className="muted">
                    {Object.entries(s.manifest_check.checks as Record<string, { expected: unknown; observed: unknown; match: boolean }>)
                      .map(([k, c]) => `${k.replace(/_/g, " ")}: expected ${String(c.expected)}, observed ${String(c.observed)}${c.match ? "" : " ✗"}`)
                      .join(" · ")}
                  </div>
                ) : null}
              </dd>
            </>
          ) : null}
          <dt>Artefacts</dt>
          <dd>
            {s.artefacts.filter((a) => a.page_index === 0).length ? (
              <details className="inline">
                <summary className="muted">
                  {s.artefacts.filter((a) => a.page_index === 0).length} document-level artefacts, plus one immutable JSON artefact per page
                </summary>
                {s.artefacts
                  .filter((a) => a.page_index === 0)
                  .map((a) => (
                    <div key={a.object_key} className="mono muted">
                      {a.stage} · {a.tool_version} · <code>{a.object_key}</code> · {a.size_bytes} B
                    </div>
                  ))}
              </details>
            ) : (
              <span className="muted">none yet</span>
            )}
          </dd>
        </dl>
      </Section>

      <Section
        id="pages"
        title="Page inventory"
        summary={!pages.data ? "not inventoried yet" : `${pages.data.pages.length} pages · ${flaggedCount} flagged (OCR, low quality, label conflict, rotation, no text)`}
      >
        {!pages.data ? (
          <p className="muted">Not inventoried yet.</p>
        ) : (
          <>
            <p className="muted">
              {allPages ? (
                <>
                  Showing all {pages.data.pages.length} pages. <Link href={`/sources/${id}?pages=flagged#pages`}>Show only the {flaggedCount} flagged pages</Link>
                </>
              ) : (
                <>
                  Showing the {flaggedCount} flagged pages. <Link href={`/sources/${id}?pages=all#pages`}>Show all {pages.data.pages.length} pages</Link>
                </>
              )}
            </p>
            {pageRows.length === 0 ? (
              <p className="muted">No page is flagged.</p>
            ) : (
              <div className="table-wrap">
                <table className="compact">
                  <thead>
                    <tr>
                      <th>Page</th>
                      <th>Printed label</th>
                      <th>Class</th>
                      <th>Flags</th>
                      <th>Text chars</th>
                      <th>Images / drawings</th>
                      <th>Roles (from localisation)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageRows.map((p) => (
                      <tr key={p.page_index}>
                        <td className="mono">{p.page_index}</td>
                        <td title={p.triage_rationale ?? undefined}>
                          {p.printed_label ?? <span className="muted">—</span>}
                          {p.label_source === "declared" ? <span className="muted"> declared</span> : null}
                          {p.quality_flags.some((f) => f === "label_conflict" || f === "label_off_rule") ? (
                            <>
                              {" "}
                              <span className="badge" data-tone="warn">conflict</span>
                            </>
                          ) : null}
                        </td>
                        <td title={p.triage_rationale ?? "not triaged yet"}>
                          <span className="badge" data-tone={p.page_class === "unknown" ? "unknown" : "neutral"}>{p.page_class.replace(/_/g, " ")}</span>
                        </td>
                        <td>
                          {p.rotation ? <span className="badge" data-tone="warn">{p.rotation}°</span> : null}
                          {!p.has_text_layer ? <span className="badge" data-tone="warn">no text layer</span> : null}
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
                        <td className="mono">{p.text_chars}</td>
                        <td className="mono">
                          {p.image_count} / {p.drawing_count}
                        </td>
                        <td className="muted">{(rolesByPage.get(p.page_index) ?? []).map((r) => r.replace(/_/g, " ")).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Section>
    </>
  );
}
