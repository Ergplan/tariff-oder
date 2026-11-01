"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../../client/actions";

/** A reviewer's decision on one label: an alias to a taxonomy line (a suggestion or any code),
 * or "not a line"; withdrawn while the mapping is still a draft. */
export default function Decide({
  commission,
  label,
  example,
  decision,
  suggestions,
  canDecide,
}: {
  commission: string;
  label: string;
  example: string | null;
  decision: { kind: string; code: string | null; note: string | null; by: string } | null;
  suggestions: { code: string; label: string; score: number }[];
  canDecide: boolean;
}) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [error, setError] = useState<ErrorResponse | null>(null);
  const base = `arr/mappings/${encodeURIComponent(commission)}/decisions`;
  async function put(kind: "alias" | "not_a_line", c?: string) {
    setError(null);
    const r = await call(base, "PUT", { label, kind, code: c ?? null, example });
    if (!r.ok) return setError(r.error);
    router.refresh();
  }
  if (decision) {
    return (
      <span>
        <span className="badge" data-tone={decision.kind === "alias" ? "ok" : "neutral"}>
          {decision.kind === "alias" ? `→ ${decision.code}` : "not a line"}
        </span>{" "}
        <span className="muted">{decision.by}</span>{" "}
        {canDecide ? (
          <button
            type="button"
            data-tone="plain"
            onClick={async () => {
              const r = await call(`${base}?label=${encodeURIComponent(label)}`, "DELETE");
              if (!r.ok) return setError(r.error);
              router.refresh();
            }}
          >
            Withdraw
          </button>
        ) : null}
        {error ? <ErrorBanner error={error} /> : null}
      </span>
    );
  }
  if (!canDecide) {
    return <span className="muted">{suggestions.map((s) => s.code).join(", ") || "—"}</span>;
  }
  return (
    <span>
      {suggestions.map((s) => (
        <button key={s.code} type="button" data-tone="plain" title={`${s.label} (word overlap ${s.score})`} onClick={() => void put("alias", s.code)}>
          → {s.code}
        </button>
      ))}
      <input value={code} onChange={(e) => setCode(e.target.value.trim().toUpperCase())} placeholder="other code" size={12} />
      <button type="button" data-tone="plain" disabled={!code} onClick={() => void put("alias", code)}>
        Set
      </button>
      <button type="button" data-tone="plain" onClick={() => void put("not_a_line")}>
        Not a line
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </span>
  );
}
