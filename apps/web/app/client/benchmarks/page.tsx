import Link from "next/link";
import type { components } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";

export const dynamic = "force-dynamic";

type Input = { line_code: string; value: string; unit: string; order: string; page: number | null };
type Cell = { value: string | null; reason: string | null; inputs: Input[]; rank?: number };
type Row = { code: string; name: string; commission: string; state: string | null; is_fixture: boolean; values: Record<string, Cell> };
type Metric = { id: string; label: string; unit: string; words: string };
type Stat = { n: number; min?: string; median?: string; max?: string };

const UNIT: Record<string, string> = { INR_per_kWh: "Rs/kWh", percent: "%" };
const VOICES = ["approved", "petitioned", "final_true_up", "provisional_true_up", "actual"];

function fyNow(): string {
  const d = new Date();
  const y = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
  return `FY${y}-${String((y + 1) % 100).padStart(2, "0")}`;
}

/**
 * Benchmarks across licensees (increment 34): ratios derived from reviewed, published ARR facts
 * of one year and voice — every value with the facts, orders and pages it comes from, the
 * median of the peers, and the rank (1 = lowest).  Derived, never stored, never a fact.
 */
export default async function BenchmarksPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const fy = sp.fy && /^FY\d{4}-\d{2}$/.test(sp.fy) ? sp.fy : fyNow();
  const voice = VOICES.includes(sp.voice ?? "") ? sp.voice! : "approved";
  const fixtures = sp.fixtures === "1";
  const highlight = sp.highlight ?? "";
  const q = new URLSearchParams({ fiscal_year: fy, value_type: voice, include_fixtures: String(fixtures) });
  if (sp.commission) q.set("commission", sp.commission);
  const res = await apiTry<components["schemas"]["ArrBenchmarksOut"]>(`/arr/benchmarks?${q.toString()}`);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const b = res.data;
  const metrics = b.metrics as unknown as Metric[];
  const rows = b.licensees as unknown as Row[];
  const stats = b.stats as unknown as Record<string, Stat>;
  const link = (over: Record<string, string>) => {
    const p = new URLSearchParams({ fy, voice, ...(fixtures ? { fixtures: "1" } : {}), ...(highlight ? { highlight } : {}), ...over });
    return `/client/benchmarks?${p.toString()}`;
  };
  return (
    <>
      <p>
        <Link href="/client">← ARR workspace</Link>
      </p>
      <h1>
        Benchmarks{" "}
        <span className="badge" data-tone="warn">
          derived
        </span>
      </h1>
      <p className="muted">{b.note}</p>
      <form className="form-grid" method="get" action="/client/benchmarks">
        <label>
          Financial year
          <input name="fy" defaultValue={fy} pattern="FY\d{4}-\d{2}" />
        </label>
        <label>
          Voice
          <select name="voice" defaultValue={voice}>
            {VOICES.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          Highlight licensee
          <input name="highlight" defaultValue={highlight} placeholder="NPCL" />
        </label>
        <label>
          <span>
            <input type="checkbox" name="fixtures" value="1" defaultChecked={fixtures} /> include FIXTURE licensees
          </span>
        </label>
        <button type="submit">Show</button>
      </form>
      {rows.length === 0 ? (
        <div className="banner" data-tone="neutral">
          No licensee has reviewed, published ARR facts of {fy} ({voice}) yet{fixtures ? "" : " (fixtures left out)"}. Benchmarks appear as orders are read, reviewed and published. <Link href={link({ fixtures: "1" })}>Include fixtures</Link> ·{" "}
          <Link href="/client/library">Library coverage →</Link>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Licensee</th>
                {metrics.map((m) => (
                  <th key={m.id} title={m.words}>
                    {m.label} <span className="muted">({UNIT[m.unit] ?? m.unit})</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.code} style={r.code === highlight ? { background: "var(--highlight, #fff7d6)" } : undefined}>
                  <td>
                    <Link href={`/client/licensees/${encodeURIComponent(r.code)}`} className="mono">
                      {r.code}
                    </Link>{" "}
                    <span className="muted">{r.commission}</span>
                    {r.is_fixture ? (
                      <span className="badge" data-tone="fixture">
                        FIXTURE
                      </span>
                    ) : null}
                  </td>
                  {metrics.map((m) => {
                    const c = r.values[m.id];
                    const origin = c.inputs.map((i) => `${i.line_code} ${i.value} ${i.unit} — ${i.order} p.${i.page}`).join("\n");
                    return (
                      <td key={m.id} className="mono" title={c.value ? `${m.words}\n${origin}` : (c.reason ?? "")}>
                        {c.value ?? <span className="muted">—</span>}
                        {c.value && stats[m.id]?.n > 1 ? <span className="muted"> #{c.rank}</span> : null}
                      </td>
                    );
                  })}
                </tr>
              ))}
              <tr>
                <td className="muted">median (min – max)</td>
                {metrics.map((m) => {
                  const s = stats[m.id];
                  return (
                    <td key={m.id} className="mono muted">
                      {s?.n ? `${s.median} (${s.min} – ${s.max}), n=${s.n}` : "—"}
                    </td>
                  );
                })}
              </tr>
            </tbody>
          </table>
        </div>
      )}
      <h2>How each ratio is computed</h2>
      <ul>
        {metrics.map((m) => (
          <li key={m.id}>
            <strong>{m.label}</strong>: {m.words}.
          </li>
        ))}
      </ul>
      <p className="muted">Hover a value for the facts, orders and pages it comes from; a dash means a reviewed input is missing (hover for which).</p>
    </>
  );
}
