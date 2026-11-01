import Link from "next/link";
import type { CoverageOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { KIND_SHORT, LEVELS, Level } from "../levels";
import { Eyebrow } from "../studio";

export const dynamic = "force-dynamic";

type Cell = { level: string; entry_id: string };
type Licensee = { code: string; name: string; licensee_kind: string; cells: Record<string, Cell> };
type Commission = { code: string; name: string; commission_wide: Record<string, Cell>; licensees: Licensee[] };
type State = { code: string; name: string; commissions: Commission[] };

const YEAR_KINDS = ["tariff_order", "arr_true_up_order", "arr_petition"];
const PERIOD_KINDS = ["myt_order", "myt_petition", "mid_term_review"];

/**
 * The regulatory library (ADR-0019): for every state, commission and licensee, which
 * documents of the last years are known and how far each has been read.  "missing" slots
 * are expectations seeded from the registry — the gaps still to be located — never data.
 */
export default async function LibraryPage({ searchParams }: { searchParams: Promise<{ state?: string }> }) {
  const { state } = await searchParams;
  const res = await apiTry<CoverageOut>("/library/coverage");
  if (res.error || !res.data) {
    return (
      <>
        <h1>Regulatory library</h1>
        <ErrorBanner error={res.error!} />
      </>
    );
  }
  const cov = res.data;
  const states = cov.states as unknown as State[];
  const years = cov.fiscal_years;
  const shown = state ? states.filter((s) => s.code === state) : states;
  const cols = [...YEAR_KINDS.flatMap((k) => years.map((fy) => ({ key: `${k}|${fy}`, label: `${KIND_SHORT[k]} ${fy.replace("FY", "")}` }))), ...PERIOD_KINDS.map((k) => ({ key: `${k}|`, label: `${KIND_SHORT[k]} (current)` }))];
  const usedCols = cols.filter((c) => shown.some((s) => s.commissions.some((cm) => cm.licensees.some((l) => l.cells[c.key]))));
  return (
    <>
      <header className="case-head">
        <Eyebrow>Library · {states.length} states · {years.join(", ")}</Eyebrow>
        <h1>The regulatory record</h1>
        <p className="muted" style={{ maxWidth: "52rem", margin: 0 }}>
          Every state&apos;s tariff orders, true-ups, ARR petitions, MYT orders and petitions, and regulations, by licensee and year. A number from a document becomes a fact only after it is read and
          reviewed; the level says how far each document has come.
        </p>
      </header>
      <div className="cov-legend">
        {LEVELS.map((l) => (
          <span key={l}>
            <Level level={l} /> {cov.totals[l] ?? 0}
          </span>
        ))}
      </div>
      {states.length === 0 ? (
        <div className="banner" data-tone="neutral">
          The library is empty. An administrator seeds the expected documents (Library administration), then records each official URL and acquires it.
        </div>
      ) : (
        <p>
          State:{" "}
          <Link href="/client/library">all</Link>
          {states.map((s) => (
            <span key={s.code}>
              {" · "}
              <Link href={`/client/library?state=${encodeURIComponent(s.code)}`}>{s.name}</Link>
            </span>
          ))}
        </p>
      )}
      {shown.map((s) => (
        <section key={s.code}>
          <h2>{s.name}</h2>
          {s.commissions.map((c) => (
            <div key={c.code}>
              <h3>
                {c.name} <span className="mono muted">{c.code}</span>{" "}
                {Object.entries(c.commission_wide).map(([k, v]) => (
                  <span key={k} className="muted" style={{ fontSize: "0.8rem", fontWeight: 400 }}>
                    {" "}
                    {KIND_SHORT[k.split("|")[0]] ?? k}: <Level level={v.level} />
                  </span>
                ))}
              </h3>
              <div className="table-wrap">
                <table className="cov-table">
                  <thead>
                    <tr>
                      <th>Licensee</th>
                      {usedCols.map((col) => (
                        <th key={col.key}>{col.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {c.licensees.map((l) => (
                      <tr key={l.code}>
                        <td>
                          <Link href={`/client/licensees/${encodeURIComponent(l.code)}`}>{l.code}</Link>
                          <span className="muted"> {l.licensee_kind === "transmission" ? "(transmission)" : ""}</span>
                        </td>
                        {usedCols.map((col) => (
                          <td key={col.key}>{l.cells[col.key] ? <Level level={l.cells[col.key].level} /> : <span className="muted">—</span>}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      ))}
    </>
  );
}
