"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ErrorResponse, SourceSummary } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

/** Who reviews this order.  "Take it" assigns the caller; an administrator may type any reviewer. */
export function AssignForm({ sourceId, assignedTo, me, isAdmin }: { sourceId: string; assignedTo: string | null; me: string; isAdmin: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState(assignedTo ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function put(reviewer: string | null) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/sources/${sourceId}/assignment`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reviewer }),
      });
      if (!res.ok) setError(await readError(res));
      else {
        const s = (await res.json()) as SourceSummary;
        setEmail(s.assigned_to ?? "");
        router.refresh();
      }
    } catch {
      setError(networkError("The assignment"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="assign">
      <span className="muted">Reviewer:</span>{" "}
      {assignedTo ? <strong>{assignedTo}</strong> : <span className="muted">unassigned</span>}{" "}
      {assignedTo !== me ? (
        <button type="button" className="tt-btn" disabled={busy} onClick={() => void put(me)}>
          Take it
        </button>
      ) : null}
      {assignedTo ? (
        <button type="button" className="tt-btn" disabled={busy} onClick={() => void put(null)}>
          Clear
        </button>
      ) : null}
      {isAdmin ? (
        <form
          className="assign-admin"
          onSubmit={(e) => {
            e.preventDefault();
            void put(email.trim() || null);
          }}
        >
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="reviewer@…" aria-label="Reviewer email" size={28} />
          <button type="submit" className="tt-btn" disabled={busy}>
            Assign
          </button>
        </form>
      ) : null}
      {error ? (
        <div className="muted" role="alert">
          {error.message} {error.detail ?? ""}
        </div>
      ) : null}
    </div>
  );
}
