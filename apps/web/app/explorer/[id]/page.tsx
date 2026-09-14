import Link from "next/link";
import type { PublishedFactOut, TariffExplorer } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { Citations, CompletenessBannerView } from "./shared";

export const dynamic = "force-dynamic";

function applicability(f: PublishedFactOut): string {
  const a = f.applicability as Record<string, unknown>;
  return (
    Object.entries(a)
      .filter(([, v]) => v != null)
      .map(([k, v]) => `${k}=${typeof v === "object" ? ((v as { original_text?: string }).original_text ?? JSON.stringify(v)) : String(v)}`)
      .join(" · ") || "—"
  );
}

/**
 * Tariff explorer (Section 9, screen 5): category tree, rates with units and value_state,
 * applicability, conditions and citations under a completeness banner.  Every value is a
 * published fact of the current release; every number links to its cited page.
 */
export default async function TariffExplorerPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const sp = await searchParams;
  const category = typeof sp.category === "string" ? sp.category : "";
  const t = await apiTry<TariffExplorer>(`/explorer/sources/${id}/tariff${category ? `?category=${encodeURIComponent(category)}` : ""}`);
  if (t.error || !t.data) {
    return (
      <>
        <h1>Tariff explorer</h1>
        <ErrorBanner error={t.error!} />
      </>
    );
  }
  const x = t.data;
  return (
    <>
      <h1>Tariff explorer</h1>
      <p className="muted">
        <Link href="/explorer">All releases</Link> · <Link href={`/explorer/${id}/network`}>Open access and network charges</Link> ·{" "}
        <Link href={`/sources/${id}`}>Source</Link>
      </p>
      {x.status === "coverage_insufficient" || !x.completeness || !x.release ? (
        <div className="banner" data-tone="warn" role="status">
          <strong>Coverage insufficient.</strong> {x.message}
        </div>
      ) : (
        <>
          <CompletenessBannerView b={x.completeness} unresolved={x.unresolved_items} />
          <form method="get" className="card" aria-label="Category filter">
            <label>
              Category <input name="category" defaultValue={category} size={12} />
            </label>{" "}
            <button type="submit">Show</button>{" "}
            {category ? <Link href={`/explorer/${id}`}>clear</Link> : null}
          </form>
          {x.categories.length === 0 ? <p className="muted">No published retail-tariff fact matches.</p> : null}
          {x.categories.map((c) => (
            <section key={c.category_code} className="card" aria-label={`Category ${c.category_code}`}>
              <h2>
                <span className="mono">{c.category_code}</span> <span className="muted">{c.facts} published fact(s)</span>
              </h2>
              {Object.entries(c.components).map(([component, facts]) => (
                <div key={component} className="table-wrap">
                  <table>
                    <caption>{component}</caption>
                    <thead>
                      <tr>
                        <th>Value</th>
                        <th>State</th>
                        <th>Unit</th>
                        <th>Applies to</th>
                        <th>Review</th>
                        <th>Citation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {facts.map((f) => (
                        <tr key={f.fact_id}>
                          <td className="mono">
                            {f.value ?? (f.reference_target ?? "—")}
                            {f.original_text && f.original_text !== f.value ? <div className="muted">“{f.original_text}”</div> : null}
                          </td>
                          <td>
                            <code>{f.value_state}</code>
                            {f.decision_status ? <div className="muted">{f.decision_status}</div> : null}
                          </td>
                          <td className="mono">{[f.currency, f.per_unit, f.frequency].filter(Boolean).join(" / ") || "—"}</td>
                          <td className="muted">{applicability(f)}</td>
                          <td>
                            <span className="badge" data-tone="ok">
                              {f.review_status}
                            </span>
                            {f.is_fixture ? (
                              <>
                                {" "}
                                <span className="badge" data-tone="fixture">
                                  FIXTURE
                                </span>
                              </>
                            ) : null}
                          </td>
                          <td>
                            <Citations f={f} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
              {c.conditions.length ? (
                <div className="muted">
                  Conditions linked to this category:
                  <ul>
                    {c.conditions.map((cond, i) => (
                      <li key={i}>
                        <code>{cond}</code>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ))}
          {x.general_conditions.length ? (
            <section className="card" aria-label="General conditions">
              <h2>General conditions (published, verbatim)</h2>
              <ul>
                {x.general_conditions.map((g, i) => (
                  <li key={i}>
                    <code>{g}</code>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      )}
    </>
  );
}
