import { load } from "@/lib/db.ts";
import { GEO, SMALL } from "@/lib/geo.ts";
import { count } from "@/lib/format.ts";
import { DbDown } from "./ui.tsx";

export const dynamic = "force-dynamic";

const LEVELS = [
  ["f0", "no data"],
  ["f1", "orders listed"],
  ["f2", "orders read"],
  ["f3", "ARR figures"],
] as const;

interface StateRow { code: string; name: string; kind: string; orders: number; orders_read: number; utilities: number; with_arr: number; commissions: string | null }

function level(s: StateRow | undefined): number {
  if (!s) return 0;
  if (s.with_arr > 0) return 3;
  if (s.orders_read > 0) return 2;
  if (s.orders > 0) return 1;
  return 0;
}
function words(s: StateRow | undefined): string {
  if (!s) return "no data";
  const parts = [LEVELS[level(s)][1]];
  if (s.orders) parts.push(`${s.orders} order${s.orders === 1 ? "" : "s"}, ${s.orders_read} read`);
  if (s.utilities) parts.push(`ARR figures for ${s.with_arr} of ${s.utilities} utilities`);
  return parts.join("; ");
}

export default async function Home() {
  const res = await load(async (sql) => {
    const states = (await sql`
      WITH so AS (
        SELECT DISTINCT u.state, o.order_id, o.read_status
        FROM orders o JOIN order_utilities ou ON ou.order_id = o.order_id JOIN utilities u ON u.code = ou.utility
        UNION
        SELECT DISTINCT cs.state, o.order_id, o.read_status
        FROM orders o JOIN commission_states cs ON cs.commission = o.commission
        WHERE NOT EXISTS (SELECT 1 FROM order_utilities x WHERE x.order_id = o.order_id)
      )
      SELECT s.code, s.name, s.kind,
        (SELECT count(*) FROM so WHERE so.state = s.code)::int AS orders,
        (SELECT count(*) FROM so WHERE so.state = s.code AND so.read_status = 'read')::int AS orders_read,
        (SELECT count(*) FROM utilities u WHERE u.state = s.code)::int AS utilities,
        (SELECT count(DISTINCT a.utility) FROM v_arr a WHERE a.state = s.code)::int AS with_arr,
        (SELECT string_agg(cs.commission, ', ' ORDER BY cs.commission) FROM commission_states cs WHERE cs.state = s.code) AS commissions
      FROM states s ORDER BY s.name`) as unknown as StateRow[];
    const [totals] = await sql`
      SELECT (SELECT count(*) FROM orders) AS orders,
             (SELECT count(*) FROM orders WHERE read_status = 'read') AS orders_read,
             (SELECT count(*) FROM facts) AS facts,
             (SELECT count(*) FROM facts WHERE reviewed_by IS NOT NULL) AS reviewed,
             (SELECT count(*) FROM utilities) AS utilities,
             (SELECT count(DISTINCT utility) FROM v_arr WHERE utility <> 'TOTAL') AS utilities_with_arr,
             (SELECT count(*) FROM commissions) AS commissions,
             (SELECT count(DISTINCT reader) FROM parses) AS readers,
             (SELECT count(*) FROM paragraphs WHERE kind <> 'text') AS key_paragraphs`;
    return { states, totals };
  });
  if (!res.ok) return <DbDown state={res} />;
  const { states, totals } = res.data;
  const by = new Map(states.map((s) => [s.code, s]));
  const [, , vw, vh] = GEO.viewBox.split(" ").map(Number);

  return (
    <>
      <section aria-labelledby="h1">
        <p className="eyebrow">India · state electricity commissions · ARR orders</p>
        <h1 id="h1" className="big">What each commission approved, with the page it says it on</h1>
        <p className="plain">
          Every ARR order of India&apos;s distribution and transmission utilities that the network has found, and the figures read from it.
          Each figure keeps its order, page and the line as printed, and says how many independent readers agree on it.
        </p>
        <form className="search" action="/search" role="search">
          <label htmlFor="q" className="sr">Search orders and figures</label>
          <input id="q" name="q" type="search" placeholder="Search orders: e.g. power purchase cost disallowed" />
          <button type="submit">Search</button>
        </form>
        <div className="stats" aria-label="What the database holds">
          <div><b>{count(totals.orders)}</b><span>orders found</span></div>
          <div><b>{count(totals.orders_read)}</b><span>orders read</span></div>
          <div><b>{count(totals.facts)}</b><span>figures</span></div>
          <div><b>{count(totals.utilities_with_arr)}<small className="muted"> / {count(totals.utilities)}</small></b><span>utilities with ARR</span></div>
          <div><b>{count(totals.commissions)}</b><span>commissions</span></div>
          <div><b>{count(totals.reviewed)}</b><span>reviewed by a person</span></div>
        </div>
      </section>

      <section aria-labelledby="map-h">
        <h2 id="map-h">States and union territories</h2>
        <div className="mapgrid">
          <div>
            <svg className="map" viewBox={`0 0 ${vw} ${vh}`} role="group" aria-labelledby="map-title map-desc">
              <title id="map-title">Map of India by state and union territory</title>
              <desc id="map-desc">Each state is a link to its page, shaded by what the database holds for it. The list beside the map holds the same links.</desc>
              {GEO.states.map((g) => {
                const s = by.get(g.code);
                const lv = level(s);
                const label = `${g.name}: ${words(s)}`;
                return (
                  <a key={g.code} href={`/state/${g.code}`} aria-label={label}>
                    <title>{label}</title>
                    <path d={g.d} className={`f${lv}`} />
                    {SMALL.has(g.code) ? (
                      <>
                        <circle className={`dot f${lv}`} cx={g.cx} cy={g.cy} r={6} />
                        <circle className="hit" cx={g.cx} cy={g.cy} r={22} />
                      </>
                    ) : null}
                  </a>
                );
              })}
            </svg>
            <div className="legend" aria-label="Legend">
              {LEVELS.map(([cls, w]) => <span key={cls}><i className={cls} aria-hidden="true" />{w}</span>)}
              <span><i className="f0" style={{ borderRadius: "50%" }} aria-hidden="true" />small territory (dot)</span>
            </div>
            <p className="note">Boundaries: {GEO.source} Simplified ({GEO.simplified}).</p>
          </div>
          <div>
            <h3 style={{ marginTop: 0 }}>All states and union territories</h3>
            <ul className="statelist">
              {GEO.states.slice().sort((a, b) => a.name.localeCompare(b.name)).map((g) => {
                const s = by.get(g.code);
                const lv = level(s);
                return (
                  <li key={g.code}>
                    <a href={`/state/${g.code}`}>
                      <i className={`f${lv}`} aria-hidden="true" />
                      <span>{g.name}</span>
                      <small>{s && s.orders ? `${s.orders_read}/${s.orders} read` : "no data"}<span className="sr">: {words(s)}</span></small>
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      </section>
    </>
  );
}
