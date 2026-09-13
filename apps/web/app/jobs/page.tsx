import Link from "next/link";
import type { JobList } from "@tariff/contracts";
import { apiTry } from "@/lib/api";
import { ErrorBanner, JobBadge } from "../components";

export const dynamic = "force-dynamic";

export default async function JobsPage() {
  const jobs = await apiTry<JobList>("/jobs?limit=200");
  return (
    <>
      <h1>Jobs</h1>
      <p className="muted">PostgreSQL-backed queue: leases, heartbeats, checkpoints, bounded retries.</p>
      {jobs.error ? <ErrorBanner error={jobs.error} /> : null}
      {jobs.data ? (
        <table>
          <thead>
            <tr>
              <th>Job</th>
              <th>Type</th>
              <th>Status</th>
              <th>Stage / progress</th>
              <th>Attempts</th>
              <th>Lease</th>
              <th>Error</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.items.map((j) => (
              <tr key={j.id}>
                <td className="mono">{j.id.slice(0, 8)}</td>
                <td>{j.job_type}</td>
                <td>
                  <JobBadge status={j.status} />
                </td>
                <td>
                  {j.stage ?? "—"}{" "}
                  {j.progress?.pages_total ? (
                    <span className="muted">
                      {String(j.progress.pages_done ?? 0)}/{String(j.progress.pages_total)} pages
                    </span>
                  ) : null}
                </td>
                <td>
                  {j.attempts}/{j.max_attempts}
                </td>
                <td className="muted">
                  {j.lease_owner ? (
                    <>
                      {j.lease_owner}
                      <br />
                      heartbeat {j.heartbeat_at ? new Date(j.heartbeat_at).toLocaleTimeString() : "—"}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{j.error_type ? <span className="badge" data-tone="bad">{j.error_type}</span> : "—"}</td>
                <td>{j.source_id ? <Link href={`/sources/${j.source_id}`}>source</Link> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  );
}
