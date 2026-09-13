import type { ErrorResponse, JobStatus, SourceState } from "@tariff/contracts";
import { EXCEPTION_STATES, PIPELINE_STATES } from "@tariff/contracts";

export function ErrorBanner({ error }: { error: ErrorResponse }) {
  return (
    <div className="banner" data-tone="bad" role="alert">
      <strong>{error.message}</strong> <span className="muted">({error.error_type})</span>
      <div>{error.next_step}</div>
      {error.detail ? <div className="muted mono">{error.detail}</div> : null}
      {error.request_id ? (
        <div className="muted">
          Request id: <code>{error.request_id}</code>
        </div>
      ) : null}
    </div>
  );
}

export function StateBadge({ state }: { state: SourceState }) {
  const tone =
    state === "published" ? "ok" : state === "failed" || state === "rejected" ? "bad" : EXCEPTION_STATES.includes(state) ? "warn" : "neutral";
  return (
    <span className="badge" data-tone={tone} aria-label={`source state ${state}`}>
      {state}
    </span>
  );
}

export function JobBadge({ status }: { status: JobStatus }) {
  const tone = status === "succeeded" ? "ok" : status === "failed" ? "bad" : status === "cancelled" ? "warn" : "neutral";
  return (
    <span className="badge" data-tone={tone} aria-label={`job status ${status}`}>
      {status}
    </span>
  );
}

export function DatasetBadge({ kind }: { kind: "real" | "fixture" }) {
  return kind === "fixture" ? (
    <span className="badge" data-tone="fixture" aria-label="fixture dataset">
      FIXTURE
    </span>
  ) : (
    <span className="badge" data-tone="neutral" aria-label="real dataset">
      real
    </span>
  );
}

export function UnknownBadge({ label }: { label: string }) {
  return (
    <span className="badge" data-tone="unknown" aria-label={`${label} unknown`}>
      {label}: unknown
    </span>
  );
}

export function StageTrack({ state }: { state: SourceState }) {
  const idx = PIPELINE_STATES.indexOf(state);
  return (
    <ol className="stage-track" aria-label="Pipeline stages">
      {PIPELINE_STATES.map((s, i) => (
        <li key={s} data-done={idx >= 0 && i < idx} data-current={s === state}>
          {s}
        </li>
      ))}
      {EXCEPTION_STATES.includes(state) ? <li data-current="true">{state}</li> : null}
    </ol>
  );
}
