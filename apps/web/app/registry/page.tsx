import type { RegistryOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { DatasetBadge, ErrorBanner } from "../components";

export const dynamic = "force-dynamic";

export default async function RegistryPage() {
  const reg = await apiTry<RegistryOut>("/registry");
  return (
    <>
      <h1>Registry</h1>
      <p className="muted">
        Jurisdictions, commissions and utilities are identities only. A state is not a tariff schedule; no coverage is
        claimed for any utility listed here.
      </p>
      {reg.error ? <ErrorBanner error={reg.error} /> : null}
      {reg.data ? (
        <table>
          <thead>
            <tr>
              <th>Utility</th>
              <th>Commission</th>
              <th>Jurisdiction</th>
              <th>Dataset</th>
              <th>Reading profile</th>
              <th>Licensed area</th>
            </tr>
          </thead>
          <tbody>
            {reg.data.utilities.map((u) => {
              const c = reg.data!.commissions.find((x) => x.id === u.commission_id);
              const j = c ? reg.data!.jurisdictions.find((x) => x.id === c.jurisdiction_id) : undefined;
              return (
                <tr key={u.id}>
                  <td>
                    <strong>{u.code}</strong> <span className="muted">{u.name}</span>
                  </td>
                  <td>{c?.code ?? "?"}</td>
                  <td>{j?.name ?? "?"}</td>
                  <td>
                    <DatasetBadge kind={u.dataset_kind} />
                  </td>
                  <td className="mono">
                    {u.active_reading_profile ?? "—"}
                    {u.active_reading_profile_version ? `@${u.active_reading_profile_version}` : " (no version yet)"}
                  </td>
                  <td className="muted">{u.licensed_area ?? "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
    </>
  );
}
