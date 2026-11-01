import Link from "next/link";
import type { ArrFormulationOut, ArrHistoryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { VALUE_TYPE_LABEL } from "../../order-types";

export const dynamic = "force-dynamic";

type Fact = { value_type: string; canonical_value: string | null; canonical_unit: string | null; order: string; page: number | null; excerpt: string | null; category_code: string | null };
type Cell = { fiscal_year: string; facts: Fact[]; disallowance: { value: string; unit: string | null }[] };
type Line = { line_code: string; label: string; cells: Cell[] };

/**
 * The reviewed ARR history of one licensee (ADR-0018): every line the commission printed,
 * by year and voice, with the order and page each number came from.  These are facts only:
 * formulations (projections) are listed separately below and never mixed into this grid.
 * The disallowance (petitioned less approved, same order) is computed for display.
 */
export default async function ArrHistoryPage({ params }: { params: Promise<{ utility: string }> }) {
  const { utility } = await params;
  const code = decodeURIComponent(utility);
  const [hist, forms] = await Promise.all([
    apiTry<ArrHistoryOut>(`/arr/utilities/${encodeURIComponent(code)}/history`),
    apiTry<ArrFormulationOut[]>(`/arr/utilities/${encodeURIComponent(code)}/formulations`),
  ]);
  if (hist.error || !hist.data) {
    return (
      <>
        <h1>ARR · {code}</h1>
        <ErrorBanner error={hist.error!} />
      </>
    );
  }
  const h = hist.data;
  const lines = h.lines as unknown as Line[];
  return (
    <>
      <h1>
        ARR history · {h.utility_name} <span className="mono muted">{h.utility}</span>{" "}
        {h.is_fixture ? (
          <span className="badge" data-tone="fixture">
            FIXTURE
          </span>
        ) : null}
      </h1>
      <p className="muted">
        <span className="badge" data-tone="ok">
          facts
        </span>{" "}
        Reviewed and published numbers as the commission printed them (canonical units: Rs crore, MU, percent). Each cell names the order and page. No projection appears in this grid.
      </p>
      {lines.length ? (
        <p>
          <a href={`/api/client/arr/utilities/${encodeURIComponent(h.utility)}/history.xlsx`}>Download as Excel</a> <span className="muted">(one row per fact, with its order, page and excerpt)</span>
        </p>
      ) : null}
      {lines.length === 0 ? (
        <div className="banner" data-tone="neutral">
          No ARR fact is published for this licensee yet. Read an order&apos;s ARR from its source page, have the chapters and lines reviewed, then publish.
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Line</th>
                {h.years.map((fy) => (
                  <th key={fy}>{fy}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((ln) => (
                <tr key={ln.line_code}>
                  <td>
                    <span className="mono">{ln.line_code}</span>
                    <div className="muted">{ln.label}</div>
                  </td>
                  {h.years.map((fy) => {
                    const cell = ln.cells.find((c) => c.fiscal_year === fy);
                    return (
                      <td key={fy}>
                        {(cell?.facts ?? []).map((f, i) => (
                          <div key={i} title={`${f.order}, page ${f.page ?? "?"}: ${f.excerpt ?? ""}`}>
                            <span className="muted">{VALUE_TYPE_LABEL[f.value_type] ?? f.value_type}</span>{" "}
                            <span className="mono">{f.canonical_value ?? "—"}</span>
                            {f.category_code ? <span className="muted"> ({f.category_code})</span> : null}
                            <span className="muted"> · p.{f.page ?? "?"}</span>
                          </div>
                        ))}
                        {(cell?.disallowance ?? []).map((d, i) => (
                          <div key={`d${i}`} className="muted" title="petitioned less approved, computed for display, never stored">
                            disallowed <span className="mono">{d.value}</span>
                          </div>
                        ))}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h2>
        Formulations{" "}
        <span className="badge" data-tone="warn">
          projections
        </span>
      </h2>
      <p className="muted">Computed for target years from the facts above, assumptions and regulation parameters. Model estimates, never facts.</p>
      {forms.error ? (
        <ErrorBanner error={forms.error} />
      ) : (forms.data ?? []).length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <ul>
          {(forms.data ?? []).map((f) => (
            <li key={f.id}>
              <Link href={`/arr/${encodeURIComponent(code)}/formulations/${f.id}`}>{f.name}</Link>{" "}
              <span className="badge" data-tone={f.status === "frozen" ? "ok" : "neutral"}>
                {f.status}
              </span>{" "}
              <span className="muted">
                base {f.base_fy} → {(f.targets as { fiscal_year: string }[]).map((t) => t.fiscal_year).join(", ")} ·{" "}
                {Number((f.summary as { blocked?: number }).blocked ?? 0)} blocked
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
