import Link from "next/link";
import type { CommissionList, Me } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../components";
import { CommissionAssign } from "./commission-assign";

export const dynamic = "force-dynamic";

const STATE_TONE: Record<string, string> = { awaiting_review: "warn", localised: "warn", published: "ok", failed: "bad", rejected: "bad" };

/**
 * Commission folders: one card per commission with its utilities, their orders by state,
 * open values and the responsible reviewer.  Upload orders under a utility on the source
 * inbox; assign the commission here; the orders inherit the reviewer.
 */
export default async function CommissionsPage() {
  const [list, me] = await Promise.all([apiTry<CommissionList>("/commissions"), apiTry<Me>("/me")]);
  if (list.error || !list.data) {
    return (
      <>
        <h1>Commissions</h1>
        <ErrorBanner error={list.error!} />
      </>
    );
  }
  const isAdmin = me.data?.role === "administrator";
  return (
    <>
      <h1>Commissions</h1>
      <p className="muted">
        One folder per regulatory commission. Upload orders under a utility on the <Link href="/sources">source inbox</Link>;
        assign the commission to a reviewer here and its orders follow. Every order runs the same pipeline; a value is a
        proposal until a reviewer decides.
      </p>
      <div className="cm-grid">
        {list.data.commissions.map((c) => (
          <section className="cm-card" key={c.id}>
            <header>
              <div>
                <h2>{c.code}</h2>
                <div className="muted">
                  {c.name} · {c.jurisdiction_name}
                </div>
              </div>
              <div className="cm-stats">
                <span className="badge" data-tone={c.awaiting_review ? "warn" : "neutral"}>
                  {c.sources} order{c.sources === 1 ? "" : "s"}
                </span>{" "}
                {c.open_values ? <span className="badge" data-tone="warn">{c.open_values} open values</span> : null}
              </div>
            </header>
            <CommissionAssign code={c.code} assignedTo={c.assigned_to} isAdmin={isAdmin} />
            <table className="compact">
              <thead>
                <tr>
                  <th>Utility</th>
                  <th>Profile</th>
                  <th>Orders</th>
                </tr>
              </thead>
              <tbody>
                {c.utilities.map((u) => (
                  <tr key={u.code}>
                    <td>
                      <Link href={`/sources?utility=${encodeURIComponent(u.code)}`}>
                        <strong>{u.code}</strong>
                      </Link>{" "}
                      <span className="muted">{u.name}</span>
                    </td>
                    <td className="mono muted">{u.active_reading_profile ?? "—"}</td>
                    <td>
                      {u.sources === 0 ? (
                        <span className="muted">none yet</span>
                      ) : (
                        Object.entries(u.by_state).map(([st, n]) => (
                          <span key={st} className="badge" data-tone={STATE_TONE[st] ?? "neutral"} style={{ marginRight: 4 }}>
                            {n} {st.replace(/_/g, " ")}
                          </span>
                        ))
                      )}
                    </td>
                  </tr>
                ))}
                {c.utilities.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="muted">
                      No utilities registered under this commission yet (add one on the Registry page).
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        ))}
      </div>
    </>
  );
}
