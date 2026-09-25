"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";
import { ORDER_TYPE_LABEL, decidesWords, parseDecides } from "@/app/order-types";

type Decided = { fiscal_year: string; value_type: string };

/**
 * What the instrument is and which years it decides in which voice (ARR spec section 5).
 * Stated by an administrator and audited; the pipeline never infers it from the file.
 */
export function ClassifyForm({ sourceId, orderType, decides, isAdmin }: { sourceId: string; orderType: string | null; decides: Decided[] | null; isAdmin: boolean }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [type, setType] = useState(orderType ?? "");
  const [text, setText] = useState((decides ?? []).map((d) => `${d.fiscal_year}:${d.value_type}`).join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let parsed: Decided[] = [];
      try {
        parsed = parseDecides(text);
      } catch (err) {
        setError({ error_type: "validation_failed", message: "Decided years", next_step: "One item per year, FY2026-27:approved, separated by commas.", severity: "error", detail: (err as Error).message });
        return;
      }
      const res = await fetch(`/api/sources/${sourceId}/classification`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ order_type: type || null, decides: parsed.length ? parsed : null }),
      });
      if (!res.ok) setError(await readError(res));
      else {
        setOpen(false);
        router.refresh();
      }
    } catch {
      setError(networkError("Saving the classification"));
    } finally {
      setBusy(false);
    }
  }

  const summary = orderType ? ORDER_TYPE_LABEL[orderType] ?? orderType : "type not stated";
  const years = decidesWords(decides);
  if (!open)
    return (
      <span className="classify">
        <span title="What the instrument is and the years it decides; set by an administrator">
          {summary}
          {years ? ` · decides ${years}` : " · decided years not stated"}
        </span>
        {isAdmin ? (
          <>
            {" "}
            <button type="button" className="link" onClick={() => setOpen(true)}>
              change
            </button>
          </>
        ) : null}
      </span>
    );
  return (
    <form className="classify" onSubmit={submit}>
      <select value={type} onChange={(e) => setType(e.target.value)} disabled={busy} aria-label="Order type">
        <option value="">type not stated</option>
        {Object.keys(ORDER_TYPE_LABEL).map((k) => (
          <option key={k} value={k}>
            {ORDER_TYPE_LABEL[k]}
          </option>
        ))}
      </select>{" "}
      <input value={text} onChange={(e) => setText(e.target.value)} placeholder="FY2024-25:final_true_up, FY2026-27:approved" size={44} disabled={busy} aria-label="Decided years" />{" "}
      <button type="submit" className="tt-btn primary" disabled={busy}>
        Save
      </button>{" "}
      <button type="button" className="tt-btn" onClick={() => setOpen(false)} disabled={busy}>
        Cancel
      </button>
      {error ? (
        <div className="muted" role="alert">
          {error.message}: {error.detail ?? error.next_step}
        </div>
      ) : null}
    </form>
  );
}
