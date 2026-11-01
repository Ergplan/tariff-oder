"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../../client/actions";

const WORDS: Record<string, string> = {
  applies: "Yes, it applies",
  does_not_apply: "No",
  before_subsidy: "Before subsidy",
  after_subsidy: "After subsidy",
  sales_within_state: "Sales within the state",
  retail_sales: "All retail sales",
};

/** A reviewer's answer to one convention question of the mapping (increment 44); withdrawn
 * while the mapping is a draft.  The hint that posed it is never the answer. */
export default function Convention({
  commission,
  question,
  values,
  decision,
  canDecide,
}: {
  commission: string;
  question: string;
  values: string[];
  decision: { value: string; note: string | null; by: string } | null;
  canDecide: boolean;
}) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [error, setError] = useState<ErrorResponse | null>(null);
  const base = `arr/mappings/${encodeURIComponent(commission)}`;
  async function answer(value: string) {
    setError(null);
    const r = await call(`${base}/conventions`, "PUT", { key: question, value, note: note || null });
    if (!r.ok) return setError(r.error);
    router.refresh();
  }
  if (decision) {
    return (
      <span>
        <span className="badge" data-tone="ok">
          {WORDS[decision.value] ?? decision.value}
        </span>{" "}
        <span className="muted">
          {decision.by}
          {decision.note ? ` — ${decision.note}` : ""}
        </span>{" "}
        {canDecide ? (
          <button
            type="button"
            data-tone="plain"
            onClick={async () => {
              const r = await call(`${base}/decisions?label=${encodeURIComponent(question)}`, "DELETE");
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
  if (!canDecide) return <span className="muted">open: a reviewer answers</span>;
  return (
    <span>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="where the order says so (table, page)" size={28} />
      {values.map((v) => (
        <button key={v} type="button" data-tone="plain" onClick={() => void answer(v)}>
          {WORDS[v] ?? v}
        </button>
      ))}
      {error ? <ErrorBanner error={error} /> : null}
    </span>
  );
}
