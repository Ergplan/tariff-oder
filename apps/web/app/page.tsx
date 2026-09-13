import type { Readiness, StatusReport } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "./components";

export const dynamic = "force-dynamic";

export default async function StatusPage() {
  const ready = await apiTry<Readiness>("/readyz");
  const status = await apiTry<StatusReport>("/status");
  return (
    <>
      <h1>Status</h1>
      <p className="muted">
        Coverage is empty: no schedule has been reviewed or published. Unknown is never green; nothing on this
        page is a tariff fact.
      </p>
      {ready.error ? <ErrorBanner error={ready.error} /> : null}
      {status.error ? <ErrorBanner error={status.error} /> : null}
      {ready.data ? (
        <div className="grid">
          <div className="card">
            <div className="label">API readiness</div>
            <div className="value">{ready.data.status}</div>
          </div>
          <div className="card">
            <div className="label">Database</div>
            <div className="value">{ready.data.database.ok ? "ok" : "unavailable"}</div>
            <div className="muted mono">migration {String(ready.data.database.migration_head ?? "none")}</div>
            <div className="muted mono">pgvector {String(ready.data.database.pgvector_version ?? "missing")}</div>
          </div>
          <div className="card">
            <div className="label">Object storage</div>
            <div className="value">{ready.data.storage.ok ? "ok" : "unavailable"}</div>
            <div className="muted mono">{String(ready.data.storage.backend)}</div>
          </div>
        </div>
      ) : null}
      {status.data ? (
        <>
          <h2>Deployment</h2>
          <dl className="kv">
            <dt>Profile</dt>
            <dd>
              {status.data.deployment_profile} ({status.data.environment_name})
            </dd>
            <dt>Adapters</dt>
            <dd className="mono">
              {Object.entries(status.data.adapters)
                .map(([k, v]) => `${k}=${v}`)
                .join("  ")}
            </dd>
            <dt>Tool versions</dt>
            <dd className="mono">
              {Object.entries(status.data.tool_versions)
                .map(([k, v]) => `${k}: ${v}`)
                .join("  ")}
            </dd>
            <dt>Limits</dt>
            <dd className="mono">
              {Object.entries(status.data.limits)
                .map(([k, v]) => `${k}=${v}`)
                .join("  ")}
            </dd>
          </dl>
          <h2>Queue</h2>
          <div className="grid">
            {Object.entries(status.data.queue_depth).map(([k, v]) => (
              <div className="card" key={k}>
                <div className="label">{k}</div>
                <div className="value">{v}</div>
              </div>
            ))}
          </div>
          <h2>Datasets</h2>
          <div className="grid">
            {Object.entries(status.data.datasets).map(([k, v]) => (
              <div className="card" key={k}>
                <div className="label">{k} sources</div>
                <div className="value">{v}</div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}
