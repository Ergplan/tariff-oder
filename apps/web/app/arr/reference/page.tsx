import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { Eyebrow } from "../../client/studio";

export const dynamic = "force-dynamic";

type Filing = { id: string; commission: string; licensee: string; title: string; documents: number; hashed: number; reproduced: boolean };
type Order = { id: string; commission: string; licensees: string[]; fiscal_year: string; title: string; checks: Record<string, number>; findings: number };

/** Reference filings (milestone 13): filed petitions kept as the target a reproduction is measured against. */
export default async function ReferenceFilings() {
  const [res, orders] = await Promise.all([apiTry<Filing[]>("/arr/reference-filings"), apiTry<Order[]>("/arr/order-reproductions")]);
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  return (
    <>
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>Desk · milestone 13</Eyebrow>
        <h1>Reference filings</h1>
        <p className="muted" style={{ margin: 0, maxWidth: "46rem" }}>
          Petitions as their licensee filed them, reproduced from their records through the commission&apos;s calculation rules. A match says a draft rule computes what the
          petitioner computed — not that either is what the regulation requires.
        </p>
      </header>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Filing</th>
              <th>Licensee</th>
              <th>Documents hashed</th>
              <th>Reproduction</th>
            </tr>
          </thead>
          <tbody>
            {res.data.map((f) => (
              <tr key={f.id}>
                <td>
                  <Link href={`/arr/reference/${f.id}`}>{f.title}</Link>
                  <div className="mono muted">{f.id}</div>
                </td>
                <td className="mono">
                  {f.licensee} · {f.commission}
                </td>
                <td className="mono">
                  {f.hashed} / {f.documents}
                </td>
                <td>{f.reproduced ? <span className="badge" data-tone="ok">reproduced</span> : <span className="badge" data-tone="neutral">not yet</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h2 style={{ marginTop: "2rem" }}>Commission orders reproduced</h2>
      <p className="muted" style={{ margin: 0, maxWidth: "46rem" }}>
        Other states&apos; orders, reproduced from the figures they print with each commission&apos;s draft rules — the engine on commissions other than UPERC.
      </p>
      {orders.error || !orders.data ? (
        <ErrorBanner error={orders.error!} />
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Licensees</th>
                <th>Checks</th>
                <th style={{ textAlign: "right" }}>Findings</th>
              </tr>
            </thead>
            <tbody>
              {orders.data.map((o) => (
                <tr key={o.id}>
                  <td>
                    <Link href={`/arr/orders/${o.id}`}>{o.title}</Link>
                    <div className="mono muted">{o.id}</div>
                  </td>
                  <td className="mono">
                    {o.licensees.join(", ")} · {o.commission}
                  </td>
                  <td className="mono">
                    {Object.entries(o.checks)
                      .sort(([a], [b]) => (a === "match" ? -1 : b === "match" ? 1 : a.localeCompare(b)))
                      .map(([k, n]) => `${n} ${k}`)
                      .join(" · ")}
                  </td>
                  <td className="mono" style={{ textAlign: "right" }}>
                    {o.findings}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p style={{ marginTop: "1rem" }}>
        <Link href="/arr/rules/UPERC">UPERC calculation rules →</Link> · <Link href="/arr/rules/UERC">UERC →</Link> · <Link href="/arr/rules/MPERC">MPERC →</Link>
      </p>
    </>
  );
}
