"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse, PublishPreview, ReleaseOut } from "@tariff/contracts";

/**
 * Publication form (Section 7.1 principle 5, Section 7.2 publication).  Step 1 previews the
 * consequences for the chosen scope: what will be published, what is pending, unresolved or
 * awaiting a second reviewer, and which required items are missing.  Step 2 declares
 * completeness (`complete` fails on any missing item; `partial` lists every gap by key),
 * confirms, and sends the preview token.  The result renders only from the API's response.
 */
export function PublishForm({ sourceId, sourceVersion }: { sourceId: string; sourceVersion: number }) {
  const router = useRouter();
  const [scope, setScope] = useState<"whole_schedule" | "subset">("whole_schedule");
  const [categories, setCategories] = useState("");
  const [families, setFamilies] = useState("");
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [completeness, setCompleteness] = useState<"complete" | "partial">("partial");
  const [gapReasons, setGapReasons] = useState<Record<string, string>>({});
  const [rationale, setRationale] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [release, setRelease] = useState<ReleaseOut | null>(null);

  const list = (s: string) =>
    s
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);

  async function loadPreview() {
    setBusy(true);
    setError(null);
    setPreview(null);
    setConfirm(false);
    try {
      const res = await fetch(`/api/sources/${sourceId}/publish/preview`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scope, categories: scope === "subset" ? list(categories) : null, families: scope === "subset" ? list(families) : null }),
      });
      const json = await res.json();
      if (!res.ok) setError(json as ErrorResponse);
      else {
        const p = json as PublishPreview;
        setPreview(p);
        setCompleteness(p.missing_for_complete.length ? "partial" : "complete");
        setGapReasons(Object.fromEntries(p.gap_keys_required_for_partial.map((k) => [k, gapReasons[k] ?? ""])));
      }
    } catch {
      setError({ error_type: "provider_unavailable", message: "The preview could not reach the server.", next_step: "Retry.", severity: "error", request_id: null });
    } finally {
      setBusy(false);
    }
  }

  async function publish(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!preview || busy) return;
    setBusy(true);
    setError(null);
    const gaps = completeness === "partial" ? preview.gap_keys_required_for_partial.map((k) => ({ key: k, reason: gapReasons[k] || "not in this release" })) : [];
    try {
      const res = await fetch(`/api/sources/${sourceId}/publish`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          scope,
          categories: scope === "subset" ? list(categories) : null,
          families: scope === "subset" ? list(families) : null,
          completeness,
          gaps,
          rationale,
          expected_source_version: preview.source_version,
          preview_token: preview.preview_token,
          confirm_consequences: confirm,
        }),
      });
      const json = await res.json();
      if (!res.ok) setError(json as ErrorResponse);
      else {
        setRelease(json as ReleaseOut);
        router.refresh();
      }
    } catch {
      setError({ error_type: "provider_unavailable", message: "The publication could not reach the server.", next_step: "Retry; nothing was published.", severity: "error", request_id: null });
    } finally {
      setBusy(false);
    }
  }

  if (release) {
    return (
      <div className="banner" data-tone={release.completeness === "complete" ? "ok" : "warn"} role="status">
        Release {release.release_number} published ({release.completeness}, {release.fact_count} facts) by {release.published_by}.{" "}
        <a href={`/explorer/${sourceId}`}>Open in the explorer</a>
      </div>
    );
  }

  return (
    <form onSubmit={publish} className="card" aria-label="Publication">
      <div className="label">1 · Scope</div>
      <p>
        <label>
          <input type="radio" name="scope" checked={scope === "whole_schedule"} onChange={() => setScope("whole_schedule")} /> whole schedule
        </label>{" "}
        <label>
          <input type="radio" name="scope" checked={scope === "subset"} onChange={() => setScope("subset")} /> explicit subset
        </label>
      </p>
      {scope === "subset" ? (
        <p>
          <label>
            Categories (comma-separated) <input value={categories} onChange={(e) => setCategories(e.target.value)} size={30} />
          </label>{" "}
          <label>
            Charge families <input value={families} onChange={(e) => setFamilies(e.target.value)} size={30} placeholder="wheeling_charge, oa_loss, …" />
          </label>
        </p>
      ) : null}
      <p>
        <button type="button" onClick={loadPreview} disabled={busy}>
          {busy && !preview ? "Loading consequences…" : "Show the consequences"}
        </button>
        <span className="muted"> source version {sourceVersion}</span>
      </p>

      {preview ? (
        <>
          <div className="label">2 · Consequences (must still hold when you publish)</div>
          <div className="grid">
            <div className="card">
              <div className="label">Facts to publish</div>
              <div className="value">{preview.facts_to_publish}</div>
              <div className="muted">of {preview.candidates_in_scope} candidates in scope</div>
            </div>
            <div className="card">
              <div className="label">Pending</div>
              <div className="value">{preview.pending.length}</div>
            </div>
            <div className="card">
              <div className="label">Awaiting second reviewer</div>
              <div className="value">{preview.awaiting_second_review.length}</div>
            </div>
            <div className="card">
              <div className="label">Unresolved</div>
              <div className="value">{preview.unresolved.length}</div>
            </div>
            <div className="card">
              <div className="label">Blocked by findings</div>
              <div className="value">{preview.blocked_by_findings.length}</div>
            </div>
          </div>
          {preview.blocked_by_findings.length ? (
            <div className="banner" data-tone="bad">
              {preview.blocked_by_findings.length} approved candidate(s) still carry blocking validator findings; correct or reject them
              before publishing.
            </div>
          ) : null}
          {preview.missing_for_complete.length ? (
            <div className="banner" data-tone="warn">
              A <strong>complete</strong> declaration would be refused. Missing:
              <ul>
                {preview.missing_for_complete.map((m, i) => (
                  <li key={i}>
                    <span className="mono">{m.key}</span> — {m.reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="banner" data-tone="ok">Nothing required is missing: the release can be declared complete.</div>
          )}
          {preview.prior_release ? (
            <p className="muted">
              This will supersede release {preview.prior_release.release_number} ({preview.prior_release.completeness},{" "}
              {preview.prior_release.fact_count} facts). Releases are cumulative.
            </p>
          ) : null}

          <div className="label">3 · Completeness declaration</div>
          <p>
            <label>
              <input type="radio" name="completeness" checked={completeness === "complete"} onChange={() => setCompleteness("complete")} disabled={preview.missing_for_complete.length > 0} /> complete
            </label>{" "}
            <label>
              <input type="radio" name="completeness" checked={completeness === "partial"} onChange={() => setCompleteness("partial")} /> partial, with listed gaps
            </label>
          </p>
          {completeness === "partial" ? (
            <div className="table-wrap">
              <table>
                <caption>Every gap must be declared with a reason; the release is labelled partial everywhere</caption>
                <thead>
                  <tr>
                    <th>Gap key</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.gap_keys_required_for_partial.map((k) => (
                    <tr key={k}>
                      <td className="mono">{k}</td>
                      <td>
                        <input value={gapReasons[k] ?? ""} onChange={(e) => setGapReasons({ ...gapReasons, [k]: e.target.value })} size={50} placeholder="why this stays out of the release" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          <p>
            <label>
              Rationale (required)
              <br />
              <textarea value={rationale} onChange={(e) => setRationale(e.target.value)} rows={2} cols={70} />
            </label>
          </p>
          <p>
            <label>
              <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /> I have read the consequences above;
              publish {preview.facts_to_publish} fact(s) as a {completeness} release. Published decisions become irreversible.
            </label>
          </p>
          <button type="submit" disabled={busy || !confirm || rationale.trim().length < 5 || preview.facts_to_publish === 0}>
            {busy ? "Publishing…" : "Publish"}
          </button>
        </>
      ) : null}
      {error ? (
        <div className="banner" data-tone="bad" role="alert" style={{ marginTop: "0.75rem" }}>
          <strong>{error.message}</strong> <span className="muted">({error.error_type})</span>
          <div>{error.next_step}</div>
          {error.detail ? <div className="muted mono">{error.detail}</div> : null}
          {error.extra ? <pre className="muted">{JSON.stringify(error.extra, null, 2)}</pre> : null}
          {error.error_type === "conflict_stale_version" ? <div className="muted">The order changed since the preview: show the consequences again.</div> : null}
        </div>
      ) : null}
    </form>
  );
}
