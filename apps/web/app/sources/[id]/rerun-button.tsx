"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ErrorResponse, JobSummary } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

type Stage = "extract_source" | "grid_source" | "parse_source";
const LABEL: Record<Stage, string> = {
  extract_source: "Re-run extraction (new rules, same tables)",
  grid_source: "Re-run from structure (tables re-analysed, then extraction)",
  parse_source: "Re-run from parse (pages re-read; localisation must be confirmed again)",
};

/**
 * Queue a stage re-run from the page (administrators).  The worker picks it up on its
 * next scheduled run; downstream stages chain.  Pending values are replaced; decided
 * values are kept and flagged stale if the new reading no longer produces them.
 */
export function RerunButton({ sourceId }: { sourceId: string }) {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("extract_source");
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<JobSummary | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/sources/${sourceId}/stages/rerun`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ job_type: stage }),
      });
      if (!res.ok) setError(await readError(res));
      else {
        setJob((await res.json()) as JobSummary);
        router.refresh();
      }
    } catch {
      setError(networkError("The re-run request"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rerun">
      <select value={stage} onChange={(e) => setStage(e.target.value as Stage)} disabled={busy} aria-label="Stage to re-run">
        {(Object.keys(LABEL) as Stage[]).map((k) => (
          <option key={k} value={k}>
            {LABEL[k]}
          </option>
        ))}
      </select>{" "}
      <button type="button" className="tt-btn" disabled={busy} onClick={() => void run()}>
        {busy ? "Queuing…" : "Queue it"}
      </button>
      {job ? (
        <span className="muted">
          {" "}
          Queued job <code>{job.id.slice(0, 8)}</code>; the worker runs within five minutes. Watch the Jobs page.
        </span>
      ) : null}
      {error ? (
        <div className="muted" role="alert">
          {error.message} {error.detail ?? ""}
        </div>
      ) : null}
    </div>
  );
}
