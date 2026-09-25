import Link from "next/link";
import type { ArrTaxonomyOut } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";

export const dynamic = "force-dynamic";

type Item = ArrTaxonomyOut["line_items"][number];

const BRANCH_TITLE: Record<string, string> = {
  E: "Energy (distribution)",
  T: "Transmission licensee",
  C: "Costs (ARR components)",
  L: "Less: income set off against costs",
  R: "Revenue requirement and gap",
  K: "Capital, assets and funding",
  X: "Detail tables",
};

/**
 * The ARR taxonomy as the app reads it (Milestone 12, ARR spec section 2): every line item
 * with its unit, kind and generic aliases, grouped by branch and nested by parent; the
 * value types, the reason categories and the arithmetic identities.  Read-only: the files
 * in packages/arr-taxonomy are the source, and a reviewer changes them through the
 * hand-mapping, not here.
 */
export default async function ArrTaxonomyPage() {
  const res = await apiTry<ArrTaxonomyOut>("/arr/taxonomy");
  if (res.error || !res.data) {
    return (
      <>
        <h1>ARR taxonomy</h1>
        <ErrorBanner error={res.error!} />
      </>
    );
  }
  const t = res.data;
  const items = t.line_items as Item[];
  const children = new Map<string | null, Item[]>();
  for (const it of items) (children.get(it.parent as string | null) ?? children.set(it.parent as string | null, []).get(it.parent as string | null)!).push(it);
  const roots = children.get(null) ?? [];
  const leaves = items.filter((i) => i.kind !== "group").length;

  function Row({ it, depth }: { it: Item; depth: number }) {
    const kids = children.get(it.code as string) ?? [];
    return (
      <>
        <tr data-kind={String(it.kind)} data-depth={depth}>
          <td className="mono" style={{ paddingLeft: `${0.5 + depth * 1.1}rem` }}>
            {String(it.code)}
          </td>
          <td>
            {String(it.label)}
            {it.by_category ? <span className="badge" data-tone="neutral" title="one row per tariff category or per user">per category</span> : null}
            {it.sign === -1 ? <span className="badge" data-tone="warn" title="printed as a deduction">less</span> : null}
            {it.note ? <div className="muted">{String(it.note)}</div> : null}
          </td>
          <td className="mono">{it.unit ? String(it.unit) : ""}</td>
          <td>
            <span className="badge" data-tone={it.kind === "computed" ? "warn" : it.kind === "detail" ? "neutral" : "ok"}>
              {String(it.kind)}
            </span>{" "}
            {it.branch !== "shared" ? <span className="muted">{String(it.branch)}</span> : null}
          </td>
          <td className="muted arr-aliases">{(it.aliases as string[]).join(" · ")}</td>
        </tr>
        {kids.map((k) => (
          <Row key={String(k.code)} it={k} depth={depth + 1} />
        ))}
      </>
    );
  }

  return (
    <>
      <h1>ARR taxonomy</h1>
      <p className="muted">
        Version {t.version} · {leaves} line items · {t.identities.length} identities · canonical units {Object.values(t.canonical_units).join(", ")} · mappings on file:{" "}
        {Object.entries(t.mappings)
          .map(([c, v]) => `${c} v${v[v.length - 1]}`)
          .join(", ") || "none"}
        . <span title={t.status}>Status: {t.status}</span>
      </p>
      <p className="muted">
        The specification is <code>docs/arr-spec.md</code>; the files are <code>packages/arr-taxonomy/</code>. A printed line that the generic aliases do not place goes to the commission mapping&apos;s
        unplaced list from <code>tariff-api arr-scan</code>, where a reviewer decides.
      </p>
      <h2>Voices and reasons</h2>
      <p>
        <strong>Value types:</strong> {t.value_types.map((v) => `${v.code} (${v.label})`).join("; ")}.
      </p>
      <p>
        <strong>Reason categories:</strong> {t.reason_categories.map((v) => `${v.code} (${v.label})`).join("; ")}.
      </p>
      {roots.map((root) => (
        <section key={String(root.code)} className="arr-branch">
          <h2>
            <span className="mono">{String(root.code)}</span> {BRANCH_TITLE[String(root.code)] ?? String(root.label)}
          </h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Line item</th>
                  <th>Unit</th>
                  <th>Kind</th>
                  <th>Generic aliases</th>
                </tr>
              </thead>
              <tbody>
                {(children.get(String(root.code)) ?? []).map((it) => (
                  <Row key={String(it.code)} it={it} depth={0} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      <h2>Identities (validators)</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Id</th>
              <th>Check</th>
              <th>Expression</th>
              <th>Severity</th>
            </tr>
          </thead>
          <tbody>
            {t.identities.map((i) => (
              <tr key={String(i.id)}>
                <td className="mono">{String(i.id)}</td>
                <td>
                  {String(i.name)}
                  {i.note ? <div className="muted">{String(i.note)}</div> : null}
                </td>
                <td className="mono arr-expr">{String(i.expression)}</td>
                <td>
                  <span className="badge" data-tone={i.severity === "blocking" ? "bad" : "warn"}>
                    {String(i.severity)}
                  </span>
                  {i.cross_order ? <span className="badge" data-tone="neutral">cross-order</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        <Link href="/commissions">Commissions</Link> · <Link href="/sources">Source inbox</Link>
      </p>
    </>
  );
}
