"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse, LocalisationRegionOut } from "@tariff/contracts";

/**
 * A reviewer's comment on one detected region, with the switch that tells the stages to
 * leave it alone.  Excluding is how the reviewer says "this is not the thing we want" —
 * e.g. a banking passage about the utility's own inter-state banking rather than the
 * open-access banking rule — without redrawing the region set.  Saved through the API,
 * versioned against the localisation record, audited; the note follows the family into
 * the review checklist.
 */
export function RegionNote({
  sourceId,
  region,
  version,
  editable,
}: {
  sourceId: string;
  region: LocalisationRegionOut;
  version: number;
  editable: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(region.reviewer_note ?? "");
  const [excluded, setExcluded] = useState(region.excluded);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/sources/${sourceId}/localisation/regions/${region.id}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ note, excluded, expected_version: version }),
      });
      if (!res.ok) setError((await res.json()) as ErrorResponse);
      else {
        setOpen(false);
        router.refresh();
      }
    } catch {
      setError({
        error_type: "provider_unavailable",
        message: "The note could not reach the server.",
        next_step: "Check your connection and retry; nothing was recorded.",
        severity: "error",
        request_id: null,
      });
    } finally {
      setBusy(false);
    }
  }

  const saved = region.reviewer_note ? (
    <div className={region.excluded ? "note excluded" : "note"}>
      {region.excluded ? <span className="badge" data-tone="bad">excluded</span> : <span className="badge" data-tone="neutral">note</span>}{" "}
      {region.reviewer_note}
      <div className="muted">
        {region.annotated_by} · {region.annotated_at ? new Date(region.annotated_at).toLocaleString() : ""}
      </div>
    </div>
  ) : null;

  if (!editable) return saved ?? <span className="muted">—</span>;
  if (!open) {
    return (
      <>
        {saved}
        <button type="button" className="link" onClick={() => setOpen(true)}>
          {region.reviewer_note ? "edit" : "add a comment"}
        </button>
      </>
    );
  }
  return (
    <form onSubmit={save} className="note-form" aria-label="Region comment">
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        minLength={5}
        required
        placeholder="what this region is, and why it does or does not belong"
      />
      <label>
        <input type="checkbox" checked={excluded} onChange={(e) => setExcluded(e.target.checked)} /> Exclude from extraction (the stages skip
        these pages; the note is shown on the family in the review checklist)
      </label>
      <div>
        <button type="submit" disabled={busy || note.trim().length < 5}>
          {busy ? "Saving…" : "Save comment"}
        </button>{" "}
        <button type="button" className="link" onClick={() => setOpen(false)}>
          cancel
        </button>
      </div>
      {error ? (
        <div className="banner" data-tone="bad" role="alert">
          <strong>{error.error_type}</strong>: {error.message} — {error.next_step}
        </div>
      ) : null}
    </form>
  );
}
