import type { MeOut, RegistryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import NewCaseForm from "./new-case-form";

export const dynamic = "force-dynamic";

/** Start an ARR process (ADR-0019): organisation, licensee, filing and years. */
export default async function NewCasePage({ searchParams }: { searchParams: Promise<{ utility?: string }> }) {
  const { utility } = await searchParams;
  const [me, reg] = await Promise.all([apiTry<MeOut>("/me"), apiTry<RegistryOut>("/registry")]);
  if (me.error || !me.data) return <ErrorBanner error={me.error!} />;
  if (reg.error || !reg.data) return <ErrorBanner error={reg.error!} />;
  const orgs = (me.data.organisations ?? []).filter((o) => o.role !== "viewer");
  const licensees = reg.data.utilities
    .filter((u) => u.licensee_kind !== "generation")
    .map((u) => ({ code: u.code, name: u.name, fixture: u.dataset_kind === "fixture" }))
    .sort((a, b) => a.code.localeCompare(b.code));
  return (
    <>
      <h1>Start an ARR process</h1>
      <p className="muted">
        A case prepares one filing for one licensee: the ARR of the year after the base year, or every year of a multi-year control period. The base year is the last year with reviewed figures
        (its final true-up, else its approval).
      </p>
      {orgs.length === 0 ? (
        <div className="banner" data-tone="warn">
          You need the editor or owner role in a client organisation to start a case.
        </div>
      ) : (
        <NewCaseForm orgs={orgs.map((o) => ({ id: o.id, name: o.name }))} licensees={licensees} initialUtility={utility ?? ""} />
      )}
    </>
  );
}
