import Link from "next/link";
import type { NetworkExplorer, PublishedFactOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import { Citations, CompletenessBannerView } from "../shared";

export const dynamic = "force-dynamic";

const LABELS: Record<string, string> = {
  wheeling_charge: "Wheeling charges",
  oa_loss: "Open-access losses (billing)",
  distribution_loss_approved: "Distribution loss trajectory (ARR)",
  cross_subsidy_surcharge: "Cross-subsidy surcharge",
  additional_surcharge: "Additional surcharge",
  banking_rule: "Banking",
  green_tariff: "Green tariff",
  transmission_reference: "Transmission references",
};

function derivation(f: PublishedFactOut): string {
  const d = f.derivation as { rule?: string; inputs?: Record<string, unknown> } | null;
  if (!d) return "—";
  const inputs = Object.entries(d.inputs ?? {})
    .map(([k, v]) => `${k}=${typeof v === "object" && v && "value" in (v as object) ? String((v as { value: unknown }).value) : String(v)}`)
    .join(" · ");
  return `${d.rule ?? "?"}${inputs ? `: ${inputs}` : ""}`;
}

/**
 * Open access and network charges (Section 9, screen 6a): per utility and year, wheeling,
 * losses by role, CSS with its computed / cap / approved inputs, additional surcharge with
 * its decision status, banking, green tariff and transmission references, each with
 * citation and review state.  A family with no published fact says so (and shows the
 * reviewed disposition when one exists); it never shows a candidate.
 */
export default async function NetworkExplorerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const n = await apiTry<NetworkExplorer>(`/explorer/sources/${id}/network`);
  if (n.error || !n.data) {
    return (
      <>
        <h1>Open access and network charges</h1>
        <ErrorBanner error={n.error!} />
      </>
    );
  }
  const x = n.data;
  return (
    <>
      <h1>Open access and network charges</h1>
      <p className="muted">
        <Link href="/explorer">All releases</Link> · <Link href={`/explorer/${id}`}>Tariff explorer</Link> · <Link href={`/sources/${id}`}>Source</Link>
      </p>
      {x.status === "coverage_insufficient" || !x.completeness ? (
        <div className="banner" data-tone="warn" role="status">
          <strong>Coverage insufficient.</strong> {x.message}
        </div>
      ) : (
        <CompletenessBannerView b={x.completeness} unresolved={[]} />
      )}
      {x.families.map((fam) => (
        <section key={fam.family} className="card" aria-label={LABELS[fam.family] ?? fam.family}>
          <h2>
            {LABELS[fam.family] ?? fam.family} <span className="mono muted">{fam.family}</span>{" "}
            <span className="badge" data-tone={fam.status === "published" ? "ok" : "warn"}>
              {fam.status === "published" ? `${fam.facts.length} published` : "coverage insufficient"}
            </span>
          </h2>
          {fam.status !== "published" ? (
            <p className="muted">
              {fam.message}
              {fam.disposition ? (
                <>
                  {" "}
                  Reviewed disposition: <code>{fam.disposition}</code>.
                </>
              ) : null}
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Level / applies to</th>
                    <th>Approved value</th>
                    <th>State / decision</th>
                    <th>Unit</th>
                    <th>Derivation (computed, cap, rule)</th>
                    <th>Period / utility</th>
                    <th>Citation</th>
                  </tr>
                </thead>
                <tbody>
                  {fam.facts.map((f) => {
                    const a = f.applicability as { voltage?: string | null; description?: string | null; consumer_class?: string | null };
                    return (
                      <tr key={f.fact_id}>
                        <td>{f.component_type}</td>
                        <td className="muted">{[a.voltage, a.description, a.consumer_class, f.category_code].filter(Boolean).join(" · ") || "—"}</td>
                        <td className="mono">{f.value ?? "—"}</td>
                        <td>
                          <code>{f.value_state}</code>
                          {f.decision_status ? <div className="muted">{f.decision_status}</div> : null}
                          {f.reference_target ? <div className="muted">{f.reference_target}</div> : null}
                        </td>
                        <td className="mono">{[f.currency, f.per_unit, f.frequency].filter(Boolean).join(" / ") || "—"}</td>
                        <td className="mono muted">{derivation(f)}</td>
                        <td className="mono">{[f.period, f.utility].filter(Boolean).join(" / ") || "—"}</td>
                        <td>
                          <Citations f={f} />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      ))}
    </>
  );
}
