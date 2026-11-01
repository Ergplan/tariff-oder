import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { Eyebrow } from "../../client/studio";

export const dynamic = "force-dynamic";

type Filing = { id: string; commission: string; licensee: string; title: string; documents: number; hashed: number; reproduced: boolean };

/** Reference filings (milestone 13): filed petitions kept as the target a reproduction is measured against. */
export default async function ReferenceFilings() {
  const res = await apiTry<Filing[]>("/arr/reference-filings");
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
      <p style={{ marginTop: "1rem" }}>
        <Link href="/arr/rules/UPERC">UPERC calculation rules →</Link>
      </p>
    </>
  );
}
