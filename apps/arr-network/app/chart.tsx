// A plain bar chart: per year, the latest claimed ARR (outlined bar) and the latest approved
// ARR (filled bar).  Values are also in the table next to it.
import { crore } from "@/lib/format.ts";

export interface Bar { year: string; claimed: number | null; approved: number | null }

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

export function ArrChart({ bars, title }: { bars: Bar[]; title: string }) {
  const W = 640, H = 300, L = 76, R = 12, T = 16, B = 46;
  const max = niceMax(Math.max(0, ...bars.flatMap((b) => [b.claimed ?? 0, b.approved ?? 0])));
  const pw = W - L - R, ph = H - T - B;
  const slot = pw / Math.max(1, bars.length);
  const bw = Math.min(26, slot / 2.6);
  const y = (v: number) => T + ph - (v / max) * ph;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="chart-t chart-d">
      <title id="chart-t">{title}</title>
      <desc id="chart-d">Bars per financial year: outlined, the latest claimed ARR; filled, the latest approved ARR, in Rs crore. The same values are in the table.</desc>
      {ticks.map((t) => (
        <g key={t}>
          <line className="grid" x1={L} x2={W - R} y1={y(t)} y2={y(t)} />
          <text x={L - 6} y={y(t) + 4} textAnchor="end">{crore(t).replace(/\.00$/, "")}</text>
        </g>
      ))}
      <line className="axis" x1={L} x2={L} y1={T} y2={T + ph} />
      <line className="axis" x1={L} x2={W - R} y1={T + ph} y2={T + ph} />
      <text x={12} y={T + ph / 2} transform={`rotate(-90 12 ${T + ph / 2})`} textAnchor="middle">Rs crore</text>
      {bars.map((b, i) => {
        const cx = L + slot * i + slot / 2;
        return (
          <g key={b.year}>
            {b.claimed !== null ? <rect className="claimed" x={cx - bw - 1} y={y(b.claimed)} width={bw} height={T + ph - y(b.claimed)} /> : null}
            {b.approved !== null ? <rect className="approved" x={cx + 1} y={y(b.approved)} width={bw} height={T + ph - y(b.approved)} /> : null}
            <text x={cx} y={T + ph + 16} textAnchor="middle">{b.year.replace(/^FY20/, "")}</text>
          </g>
        );
      })}
      <text x={L + pw / 2} y={H - 6} textAnchor="middle">Financial year (FY20xx-yy)</text>
      <g transform={`translate(${L + 8}, ${T + 2})`}>
        <rect className="claimed" width={10} height={10} /><text x={14} y={9}>claimed</text>
        <rect className="approved" x={80} width={10} height={10} /><text x={94} y={9}>approved (latest word)</text>
      </g>
    </svg>
  );
}
