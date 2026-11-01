"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../../client/actions";

const DECISIONS: [string, string][] = [
  ["accepted", "Accept"],
  ["accepted_with_reservations", "Accept with reservations"],
  ["rejected", "Reject"],
];

/** A checker's sign-off of one scope of a reference filing (R-ACC-2): the attestation that
 * they did not build the reproduction, a reason for anything short of acceptance, and the hash
 * of the reproduction shown on this page — a changed reproduction refuses the sign-off. */
export default function SignOff({ filingId, scopes, sha }: { filingId: string; scopes: string[]; sha: string }) {
  const router = useRouter();
  const [scope, setScope] = useState(scopes[0] ?? "filing");
  const [note, setNote] = useState("");
  const [independent, setIndependent] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [busy, setBusy] = useState(false);
  async function sign(decision: string) {
    setError(null);
    setBusy(true);
    const r = await call(`arr/reference-filings/${encodeURIComponent(filingId)}/acceptance`, "POST", {
      scope,
      decision,
      note: note || null,
      independent,
      reproduction_sha256: sha,
    });
    setBusy(false);
    if (!r.ok) return setError(r.error);
    setNote("");
    setIndependent(false);
    router.refresh();
  }
  return (
    <div style={{ display: "grid", gap: "0.6rem", maxWidth: "46rem" }}>
      <label>
        Scope{" "}
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          {scopes.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={3}
        placeholder="what you checked, and the reason for any reservation or rejection"
        style={{ width: "100%" }}
      />
      <label style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
        <input type="checkbox" checked={independent} onChange={(e) => setIndependent(e.target.checked)} />
        <span>I did not build this reproduction, its rules or its bindings, and I checked this scope myself.</span>
      </label>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
        {DECISIONS.map(([k, w]) => (
          <button key={k} type="button" data-tone={k === "rejected" ? "plain" : undefined} disabled={busy || !independent} onClick={() => void sign(k)}>
            {w}
          </button>
        ))}
      </div>
      <div className="mono muted" style={{ fontSize: "0.72rem", overflowWrap: "anywhere" }}>
        signs reproduction {sha}
      </div>
      {error ? <ErrorBanner error={error} /> : null}
    </div>
  );
}
