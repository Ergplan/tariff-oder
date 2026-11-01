"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../../client/actions";

/** The order's licensees.  A combined order decides several; each ARR value is then attributed
 * to the licensee its column or table caption names (re-read the order after changing this). */
export default function Licensees({ sourceId, licensees, canEdit }: { sourceId: string; licensees: { code: string; name: string; primary: boolean }[]; canEdit: boolean }) {
  const router = useRouter();
  const [codes, setCodes] = useState(licensees.map((l) => l.code).join(", "));
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <div className="card">
      <strong>Licensees in this order:</strong>{" "}
      {licensees.map((l) => (
        <span key={l.code} className="badge" data-tone={l.primary ? "ok" : "neutral"} title={l.name}>
          {l.code}
          {l.primary ? " (primary)" : ""}
        </span>
      ))}
      {licensees.length > 1 ? <span className="muted"> · a combined order: each value belongs to the licensee its column or table names</span> : null}
      {canEdit && !editing ? (
        <button type="button" data-tone="plain" onClick={() => setEditing(true)}>
          Edit
        </button>
      ) : null}
      {editing ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await call(`/api/sources/${sourceId}/licensees`, "PUT", { codes: codes.split(/[,\s]+/).filter(Boolean) });
            if (!r.ok) return setError(r.error);
            setEditing(false);
            router.refresh();
          }}
        >
          <label>
            Licensee codes (the primary first; same commission)
            <input value={codes} onChange={(e) => setCodes(e.target.value)} />
          </label>
          <button type="submit">Save</button> <span className="muted">Read the order again afterwards so its values are attributed.</span>
        </form>
      ) : null}
      {error ? <ErrorBanner error={error} /> : null}
    </div>
  );
}
