"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse, SourceRegistration } from "@tariff/contracts";

/**
 * Upload form.  Sends an Idempotency-Key so a double submit or a retry after a timeout
 * registers exactly one source (Section 7.1, principle 8).  Nothing is rendered as done
 * until the backend confirms it (principle 3).
 */
export function UploadForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<SourceRegistration | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [key, setKey] = useState<string>(() => crypto.randomUUID());

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const form = new FormData(e.currentTarget);
    try {
      const res = await fetch("/api/sources", { method: "POST", body: form, headers: { "Idempotency-Key": key } });
      const body = await res.json();
      if (!res.ok) {
        setError(body as ErrorResponse);
      } else {
        setResult(body as SourceRegistration);
        setKey(crypto.randomUUID());
        router.refresh();
      }
    } catch (err) {
      setError({
        error_type: "provider_unavailable",
        message: "The upload could not reach the server.",
        next_step: "Check your connection and retry; the same idempotency key is reused so nothing is duplicated.",
        severity: "error",
        detail: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="upload" onSubmit={onSubmit} aria-busy={busy}>
      <label>
        PDF file
        <input type="file" name="file" accept="application/pdf" required disabled={busy} />
      </label>
      <label>
        Dataset
        <select name="dataset_kind" defaultValue="real" disabled={busy}>
          <option value="real">real (a genuine regulatory order)</option>
          <option value="fixture">fixture (synthetic / test material, isolated from real data)</option>
        </select>
      </label>
      <label>
        Provenance URL (optional)
        <input type="url" name="provenance_url" placeholder="https://…" disabled={busy} />
      </label>
      <div>
        <button type="submit" disabled={busy}>
          {busy ? "Uploading — hashing and registering" : "Upload and register"}
        </button>
        <span className="muted"> idempotency key <code>{key.slice(0, 8)}</code></span>
      </div>
      {error ? (
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
      ) : null}
      {result ? (
        <div className="banner" data-tone={result.deduplicated ? "warn" : "ok"} role="status">
          {result.deduplicated ? (
            <>
              <strong>Already registered.</strong> Identical bytes exist as{" "}
              <a href={`/sources/${result.source.id}`}>{result.source.original_filename}</a> (SHA-256{" "}
              <code>{result.source.sha256.slice(0, 16)}…</code>). Nothing was duplicated.
            </>
          ) : (
            <>
              <strong>Registered.</strong> <a href={`/sources/${result.source.id}`}>{result.source.original_filename}</a>{" "}
              — SHA-256 <code>{result.source.sha256.slice(0, 16)}…</code>; inventory job{" "}
              {result.job ? <code>{result.job.id.slice(0, 8)}</code> : "not queued"} is {result.job?.status}.
            </>
          )}
          {result.idempotent_replay ? <div className="muted">(replayed from your earlier identical request)</div> : null}
        </div>
      ) : null}
    </form>
  );
}
