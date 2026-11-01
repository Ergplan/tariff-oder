import type { OrganisationOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { ActionButton } from "../../client/actions";
import { AddMember, CreateOrg } from "./org-admin";

export const dynamic = "force-dynamic";

/** Client organisations and their members (ADR-0019).  Administrators create organisations;
 * owners manage members (also from here). */
export default async function OrganisationsPage() {
  const list = await apiTry<OrganisationOut[]>("/organisations");
  if (list.error) return <ErrorBanner error={list.error} />;
  const full = await Promise.all((list.data ?? []).map((o) => apiTry<OrganisationOut>(`/organisations/${o.id}`)));
  return (
    <>
      <h1>Client organisations</h1>
      <h2>New organisation</h2>
      <CreateOrg />
      {full.map((r, i) =>
        r.data ? (
          <section key={r.data.id}>
            <h2>
              {r.data.name} <span className="mono muted">{r.data.code}</span>
            </h2>
            <ul>
              {(r.data.members ?? []).map((m) => (
                <li key={m.email}>
                  {m.email} <span className="badge" data-tone="neutral">{m.role}</span>{" "}
                  <ActionButton path={`organisations/${r.data!.id}/members/${encodeURIComponent(m.email)}`} method="DELETE" label="Remove" tone="plain" />
                </li>
              ))}
            </ul>
            <AddMember orgId={r.data.id} />
          </section>
        ) : (
          <ErrorBanner key={i} error={r.error!} />
        ),
      )}
    </>
  );
}
