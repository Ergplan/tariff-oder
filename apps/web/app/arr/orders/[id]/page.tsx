import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Eyebrow, Panel } from "../../../client/studio";

export const dynamic = "force-dynamic";

type Check = { category: string; output: string; result: string; filed: string | null; computed: string | null; exact: string | null; gap?: string; why: string | null };
type Binding = { binding: string; note: string | null; years: string[]; counts: Record<string, number>; checks: Check[] };
type Record_ = { record: string; title: string; sha256: string; figures: number; pages: number[]; status: string | null };
type Finding = { id: string; kind: string; title: string; detail: string; where: string[]; for: string };
type Reproduction = {
  id: string;
  commission: string;
  licensees?: string[];
  licensee?: string;
  fiscal_year: string;
  status: string;
  why?: string;
  order: { title: string; url: string; sha256: string; loaded_by?: string };
  rules: { file: string | null; count: number; approved: number; clauses_verified: number };
  records: Record_[];
  bindings: Binding[];
  counts: Record<string, number>;
  findings: Finding[];
};

const TONE: Record<string, string> = { match: "ok", differs: "warn", blocked: "danger", no_filed_value: "neutral" };
const ORDER: Record<string, number> = { match: 0, differs: 1, blocked: 2, no_filed_value: 3 };

function Counts({ counts }: { counts: Record<string, number> }) {
  return (
    <span style={{ display: "inline-flex", gap: "0.3rem", flexWrap: "wrap" }}>
      {Object.entries(counts)
        .sort(([a], [b]) => (ORDER[a] ?? 9) - (ORDER[b] ?? 9))
        .map(([k, n]) => (
        <span key={k} className="badge" data-tone={TONE[k] ?? "neutral"}>
          {n} {k.replace(/_/g, " ")}
        </span>
      ))}
    </span>
  );
}

/**
 * A commission order reproduced from its own printed figures with the commission's draft rules:
 * the order (URL, SHA-256), the records read from it, every binding's checks with the gap between
 * the unrounded computation and the printed figure, and the findings.  Nothing here is verified.
 */
export default async function OrderReproduction({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await apiTry<Reproduction>(`/arr/order-reproductions/${encodeURIComponent(id)}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const r = res.data;
  const who = r.licensees?.join(", ") ?? r.licensee ?? "";
  return (
    <>
      <p>
        <Link href="/arr/reference">← Reference filings and reproduced orders</Link>
      </p>
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>
          Reproduced order · {r.commission} · {r.fiscal_year}
          <span className="badge" data-tone="warn">
            draft rules · nothing approved
          </span>
        </Eyebrow>
        <h1>{r.order.title}</h1>
        <div className="case-meta">
          <span>
            Licensees <b>{who}</b>
          </span>
          <span>
            Rules <b>{r.rules.count}</b> draft · <b>{r.rules.approved}</b> approved · <b>{r.rules.clauses_verified}</b> clauses verified
          </span>
          <span>
            Checks <Counts counts={r.counts} />
          </span>
        </div>
        <p className="muted" style={{ maxWidth: "52rem" }}>
          {r.status.charAt(0).toUpperCase() + r.status.slice(1)}. A difference is not a failure: each binding&apos;s test bounds it by the printed precision of its inputs, and the gap column shows how far the unrounded
          computation lies from the printed figure. The order:{" "}
          <a href={r.order.url} rel="noreferrer">
            source
          </a>{" "}
          <span className="mono">SHA-256 {r.order.sha256.slice(0, 12)}…</span>
        </p>
      </header>

      <Panel num="01" title="Findings" aside="questions for the reviewer — none resolved by the build">
        {r.findings.length === 0 ? (
          <p className="muted">None.</p>
        ) : (
          <ul style={{ paddingLeft: "1.1rem" }}>
            {r.findings.map((f) => (
              <li key={f.id} style={{ marginBottom: "0.6rem" }}>
                <b className="mono">{f.id}</b> <span className="badge">{f.kind}</span> {f.title}
                <details>
                  <summary className="muted">detail</summary>
                  <p style={{ fontSize: "0.9rem" }}>{f.detail}</p>
                  <p className="muted mono" style={{ fontSize: "0.8rem" }}>
                    {f.where.join(" · ")}
                  </p>
                </details>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel num="02" title="Bindings" aside="each evaluates the draft rules on the records against the order's printed results">
        {r.bindings.map((b) => (
          <details key={b.binding} style={{ marginBottom: "0.9rem" }}>
            <summary>
              <span className="mono">{b.binding}</span> <span className="muted">{b.years.join(", ")}</span> <Counts counts={b.counts} />
            </summary>
            {b.note ? (
              <p className="muted" style={{ fontSize: "0.88rem", maxWidth: "52rem" }}>
                {b.note}
              </p>
            ) : null}
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Output</th>
                    <th style={{ textAlign: "right" }}>Printed</th>
                    <th style={{ textAlign: "right" }}>Computed</th>
                    <th style={{ textAlign: "right" }}>Gap</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {b.checks.map((c, i) => (
                    <tr key={i}>
                      <td style={{ fontSize: "0.85rem" }}>{c.category}</td>
                      <td className="mono">{c.output}</td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {c.filed ?? "—"}
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        {c.computed ?? "—"}
                      </td>
                      <td className="mono muted" style={{ textAlign: "right" }}>
                        {c.gap ?? ""}
                      </td>
                      <td>
                        <span className="badge" data-tone={TONE[c.result] ?? "neutral"}>
                          {c.result}
                        </span>
                        {c.why ? <div className="muted">{c.why}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        ))}
      </Panel>

      <Panel num="03" title="Records" aside="figures read from the order's text layer, each with its page and quote — not reviewed">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th style={{ textAlign: "right" }}>Figures</th>
                <th>Pages</th>
              </tr>
            </thead>
            <tbody>
              {r.records.map((x) => (
                <tr key={x.record}>
                  <td>
                    <span className="mono">{x.record}</span>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      {x.title}
                    </div>
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {x.figures}
                  </td>
                  <td className="mono">{x.pages.length ? `pp.${x.pages[0]}–${x.pages[1]}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {r.rules.file ? (
          <p style={{ marginTop: "0.8rem" }}>
            <Link href={`/arr/rules/${r.commission}`}>{r.commission} calculation rules →</Link>
          </p>
        ) : null}
      </Panel>
    </>
  );
}
