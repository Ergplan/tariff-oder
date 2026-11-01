import Link from "next/link";
import type { ArrCaseOut, CoverageOut, MeOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";
import { LEVELS, Level } from "./levels";

export const dynamic = "force-dynamic";

const STATUS_TONE: Record<string, string> = { drafted: "ok", frozen: "ok", formulated: "warn", closed: "neutral" };

/**
 * The client home (ADR-0019): the organisations you work for, your ARR cases and where
 * each stands, and how much of the regulatory library is available at each reading level.
 */
export default async function ClientHome() {
  const [me, cases, cov] = await Promise.all([apiTry<MeOut>("/me"), apiTry<ArrCaseOut[]>("/cases"), apiTry<CoverageOut>("/library/coverage")]);
  if (me.error || !me.data) return <ErrorBanner error={me.error!} />;
  const orgs = me.data.organisations ?? [];
  return (
    <>
      <h1>ARR workspace</h1>
      <p className="muted">
        Signed in as {me.data.email}.{" "}
        {orgs.length ? (
          <>
            Working for {orgs.map((o) => `${o.name} (${o.role})`).join(", ")}.
          </>
        ) : (
          <>You are not a member of a client organisation yet: an administrator adds you.</>
        )}
      </p>
      <div className="cards">
        <div className="card">
          <h3>Start an ARR process</h3>
          <p className="muted">Pick a licensee and the filing (annual ARR or MYT control period); the app shows what data is ready and what is missing.</p>
          {orgs.some((o) => o.role !== "viewer") ? <Link href="/client/cases/new">New ARR case →</Link> : <span className="muted">Needs the editor or owner role.</span>}
        </div>
        <div className="card">
          <h3>Regulatory library</h3>
          <p className="muted">Tariff orders, true-ups, MYT orders and petitions by state, licensee and year.</p>
          <Link href="/client/library">Open the library →</Link>
        </div>
        <div className="card">
          <h3>Licensee history</h3>
          <p className="muted">Reviewed ARR figures as each commission printed them, with order and page.</p>
          <Link href="/arr">Browse licensees →</Link>
        </div>
      </div>
      <h2>Your ARR cases</h2>
      {cases.error ? (
        <ErrorBanner error={cases.error} />
      ) : (cases.data ?? []).length === 0 ? (
        <p className="muted">No case yet.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Case</th>
                <th>Licensee</th>
                <th>Filing</th>
                <th>Years</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {(cases.data ?? []).map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={`/client/cases/${c.id}`}>{c.title}</Link>
                    <div className="muted">{c.organisation}</div>
                  </td>
                  <td>
                    {c.utility_name} <span className="mono muted">{c.utility}</span>
                  </td>
                  <td>{c.filing_kind === "myt" ? "MYT control period" : "Annual ARR"}</td>
                  <td className="mono">
                    {c.base_fy} → {(c.targets as { fiscal_year: string }[]).map((t) => t.fiscal_year).join(", ")}
                  </td>
                  <td>
                    <span className="badge" data-tone={STATUS_TONE[c.status] ?? "neutral"}>
                      {c.status}
                    </span>
                  </td>
                  <td className="muted">{new Date(c.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <h2>Library at a glance</h2>
      {cov.data ? (
        <div className="cov-legend">
          {LEVELS.map((l) => (
            <span key={l}>
              <Level level={l} /> {cov.data!.totals[l] ?? 0}
            </span>
          ))}
        </div>
      ) : null}
    </>
  );
}
