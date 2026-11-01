import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { type Norms, CONVENTION_WORDS, statusWord } from "../../atlas/data";
import { Level } from "../../levels";
import { Eyebrow, Journey, Panel } from "../../studio";

export const dynamic = "force-dynamic";

const VOICE = { final_true_up: "trued up", provisional_true_up: "provisional", approved: "approved" } as Record<string, string>;
const LINE_WORDS: Record<string, string> = {
  "E.LOSS.DIST_PCT": "Distribution loss",
  "C.OM": "Operation & maintenance",
  "C.RETURN.ROE": "Return on equity",
  "C.INT.WC": "Interest on working capital",
  "C.DEP": "Depreciation",
  "C.INT.LOAN": "Interest on loans",
};

function unit(u: string | null): string {
  return u === "INR_crore" ? "Rs Cr" : u === "percent" ? "%" : (u ?? "");
}

/**
 * A commission's ARR norms (increment 52), as the application holds them: the regulations its
 * mapping names, the conventions (stated in the mapping or decided by a reviewer), how each ARR
 * line is formed, and the norms its reviewed orders applied — each figure with its order and page.
 * A skeleton plan or mapping is labelled a working estimate; no norm value is ever invented.
 */
export default async function NormsPage({ params, searchParams }: { params: Promise<{ commission: string }>; searchParams: Promise<{ from?: string }> }) {
  const { commission } = await params;
  const { from } = await searchParams;
  const res = await apiTry<Norms>(`/arr/norms/${encodeURIComponent(commission)}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const n = res.data;
  const place = from ? await apiTry<{ state: string; state_name: string; code: string }>(`/atlas/licensees/${encodeURIComponent(from)}`) : { data: undefined };
  const confirmed = n.plan_confirmed && n.mapping_confirmed;
  const c = n.conventions;
  return (
    <>
      <Journey
        steps={[
          { label: "India", href: "/client/atlas" },
          ...(place.data ? [{ label: place.data.state_name, href: `/client/states/${place.data.state}` }, { label: place.data.code, href: `/client/licensees/${encodeURIComponent(place.data.code)}` }] : []),
          { label: `${n.commission} norms` },
        ]}
      />
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>
          Tariff norms · {n.commission}
          <span className="badge" data-tone={confirmed ? "ok" : "warn"}>
            {confirmed ? "confirmed by a reviewer" : "working estimate"}
          </span>
        </Eyebrow>
        <h1>{n.commission_name}</h1>
        <div className="case-meta">
          <span>
            Mapping <b>{n.mapping.id} v{n.mapping.version}</b> · <span title={n.mapping.status}>{statusWord(n.mapping.status)}</span>
          </span>
          <span>
            Formulation plan <b>{n.plan.id} v{n.plan.version}</b> · <span title={n.plan.status}>{statusWord(n.plan.status)}</span>
          </span>
        </div>
      </header>

      {!confirmed ? (
        <div className="banner" data-tone="warn">
          <strong>Working estimate.</strong> {n.commission}&apos;s mapping and formulation plan have not been confirmed by a reviewer against its regulations: the methods below are the
          shape of the formulation, and where a regulation fixes a value (an O&amp;M norm, a loss trajectory, a rate of return) the petitioner enters it with its clause.
          {n.plan.id === "generic-plan" ? " This commission has no plan of its own yet; the generic plan stands in." : ""}
        </div>
      ) : null}

      <Panel num="01" title="Regulations" aside={`${n.regulations.length} named · ${n.regulations_in_library.length} in the library`}>
        <dl className="kv">
          {n.regulations.map((r) => (
            <div key={r.role + r.title} style={{ display: "contents" }}>
              <dt>{r.role.replace(/_/g, " ")}</dt>
              <dd>
                {r.title}
                {r.year ? ` (${r.year})` : ""}
                {r.control_periods.length ? (
                  <div className="muted" style={{ fontSize: "0.85rem" }}>
                    Control period{" "}
                    {r.control_periods.map((cp) => `${cp.from_fy ?? "?"} → ${cp.to_fy ?? "open"}${cp.note ? ` (${cp.note})` : ""}`).join("; ")}
                  </div>
                ) : null}
                {r.amendments.length ? <div className="muted">Amendments: {r.amendments.join(", ")}</div> : null}
              </dd>
            </div>
          ))}
        </dl>
        {n.regulations_in_library.length ? (
          <div className="table-wrap" style={{ marginTop: "1rem" }}>
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Regulation in the library</th>
                  <th>Level</th>
                  <th>Official source</th>
                </tr>
              </thead>
              <tbody>
                {n.regulations_in_library.map((e, i) => (
                  <tr key={i}>
                    <td className="mono">{e.fiscal_year || "—"}</td>
                    <td>{e.title ?? e.kind}</td>
                    <td>
                      <Level level={e.level} />
                    </td>
                    <td>
                      {e.url ? (
                        <a href={e.url} target="_blank" rel="noreferrer noopener">
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted" style={{ marginBottom: 0 }}>
            No regulation of {n.commission} is in the library yet.
          </p>
        )}
      </Panel>

      <Panel num="02" title="Conventions" aside="how the commission's orders state the ARR">
        <dl className="kv">
          <dt>Return</dt>
          <dd>
            {c.return_basis.value ? c.return_basis.value.toUpperCase() : <span className="muted">to be confirmed</span>}
            {c.return_basis.note ? <div className="muted">{c.return_basis.note}</div> : null}
          </dd>
          <dt>Revenue gap</dt>
          <dd>
            {c.gap_convention.value ? CONVENTION_WORDS[c.gap_convention.value] ?? c.gap_convention.value : <span className="muted">to be confirmed</span>}
            {c.gap_convention.note ? <div className="muted">{c.gap_convention.note}</div> : null}
          </dd>
          <dt>Distribution loss</dt>
          <dd>
            {c.loss_basis.value ? CONVENTION_WORDS[c.loss_basis.value] ?? c.loss_basis.value : <span className="muted">on all retail sales unless stated</span>}
            {c.loss_basis.note ? <div className="muted">{c.loss_basis.note}</div> : null}
          </dd>
          {c.total_includes.length ? (
            <>
              <dt>Inclusive totals</dt>
              <dd>
                {c.total_includes.map((t) => (
                  <div key={t.total}>
                    <span className="mono">{t.total}</span> includes <span className="mono">{t.includes.join(", ")}</span>
                  </div>
                ))}
              </dd>
            </>
          ) : null}
          {c.decided_by_reviewer.length ? (
            <>
              <dt>Decided by a reviewer</dt>
              <dd>
                {c.decided_by_reviewer.map((d) => (
                  <div key={d.key}>
                    <span className="mono">{d.key}</span>: {CONVENTION_WORDS[d.value] ?? d.value}
                    {d.by ? <span className="muted"> — {d.by}</span> : null}
                  </div>
                ))}
              </dd>
            </>
          ) : null}
        </dl>
      </Panel>

      <Panel num="03" title="How each ARR line is formed" aside={`${n.lines.length} lines · base year: ${n.base_rule.prefer.join(" › ").replace(/_/g, " ")}`}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Line</th>
                <th>Method</th>
                <th>Inputs the petitioner supplies</th>
              </tr>
            </thead>
            <tbody>
              {n.lines.map((l) => (
                <tr key={l.line_code}>
                  <td>
                    {l.label}
                    <div className="mono muted">{l.line_code}</div>
                  </td>
                  <td>
                    <span className="method">{l.method.replace(/_/g, " ")}</span>
                    <div style={{ marginTop: "0.3rem" }}>{l.method_words}</div>
                    {l.note ? <div className="muted" style={{ fontSize: "0.82rem" }}>{l.note}</div> : null}
                  </td>
                  <td>
                    {l.method === "assumption" ? (
                      <span>the value for each year, with its source</span>
                    ) : l.parameters.length ? (
                      l.parameters.map((p) => <div key={p.key}>{p.words}</div>)
                    ) : (
                      <span className="muted">none — computed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel num="04" title="Norms as the orders applied them" aside="reviewed figures, latest year, each with its order and page">
        {n.applied.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No reviewed figure yet: the commission&apos;s orders must be read and their values approved by a reviewer before they appear here.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Licensee</th>
                  <th>Norm</th>
                  <th>Year</th>
                  <th style={{ textAlign: "right" }}>Value</th>
                  <th>Order</th>
                </tr>
              </thead>
              <tbody>
                {n.applied.map((a) => (
                  <tr key={a.licensee + a.line_code}>
                    <td className="mono">
                      <Link href={`/client/licensees/${encodeURIComponent(a.licensee)}`}>{a.licensee}</Link>
                    </td>
                    <td>
                      {LINE_WORDS[a.line_code] ?? a.line_code}
                      {a.is_fixture ? (
                        <>
                          {" "}
                          <span className="badge" data-tone="fixture">
                            fixture
                          </span>
                        </>
                      ) : null}
                    </td>
                    <td className="mono">
                      {a.fiscal_year} <span className="muted">{VOICE[a.voice] ?? a.voice}</span>
                    </td>
                    <td className="mono" style={{ textAlign: "right" }}>
                      {Number(a.value).toLocaleString("en-IN", { maximumFractionDigits: 2 })} <span className="muted">{unit(a.unit)}</span>
                    </td>
                    <td>
                      <Link href={`/sources/${a.source_id}`}>{a.order}</Link>
                      {a.page !== null ? <span className="muted">, p.{a.page}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="muted" style={{ fontSize: "0.82rem" }}>
        {n.note}
      </p>
    </>
  );
}
