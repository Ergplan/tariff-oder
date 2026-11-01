import type { MeOut, RegistryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../../components";
import NewCaseForm from "./new-case-form";
import { Eyebrow } from "../../studio";

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
      <header className="case-head">
        <Eyebrow>Petition studio · New petition</Eyebrow>
        <h1>Start a petition</h1>
        <p className="muted" style={{ maxWidth: "46rem", margin: 0 }}>
          One petition prepares one filing for one licensee: the next year&apos;s ARR, every year of a control period, a past year&apos;s true-up or the running year&apos;s review.
        </p>
      </header>
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
