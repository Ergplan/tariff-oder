"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { CommissionSummary, ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

/** The commission's reviewer; administrators change it and the orders without a reviewer follow. */
export function CommissionAssign({ code, assignedTo, isAdmin }: { code: string; assignedTo: string | null; isAdmin: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState(assignedTo ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function put(reviewer: string | null) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/commissions/${encodeURIComponent(code)}/assignment`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reviewer, cascade: true }),
      });
      if (!res.ok) setError(await readError(res));
      else {
        const c = (await res.json()) as CommissionSummary;
        setEmail(c.assigned_to ?? "");
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
      <span className="muted">Reviewer:</span> {assignedTo ? <strong>{assignedTo}</strong> : <span className="muted">unassigned</span>}
      {isAdmin ? (
        <form
          className="assign-admin"
          onSubmit={(e) => {
            e.preventDefault();
            void put(email.trim() || null);
          }}
        >
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="reviewer@…" aria-label="Reviewer email" size={26} />
          <button type="submit" className="tt-btn" disabled={busy}>
            Assign
          </button>
          {assignedTo ? (
            <button type="button" className="tt-btn" disabled={busy} onClick={() => void put(null)}>
              Clear
            </button>
          ) : null}
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
