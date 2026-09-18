"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

/** Add a distribution licensee under a commission (administrators). */
export function AddUtility({ commissionCode }: { commissionCode: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/utilities", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ code: code.trim().toUpperCase(), name: name.trim(), commission_code: commissionCode }),
      });
      if (!res.ok) setError(await readError(res));
      else {
        setCode("");
        setName("");
        setOpen(false);
        router.refresh();
      }
    } catch {
      setError(networkError("Adding the utility"));
    } finally {
      setBusy(false);
    }
  }

  if (!open)
    return (
      <button type="button" className="link" onClick={() => setOpen(true)}>
        + add a distribution company
      </button>
    );
  return (
    <form className="cm-add" onSubmit={submit}>
      <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="CODE (e.g. PVVNL)" size={12} required aria-label="Utility code" />
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name" size={36} required aria-label="Utility name" />
      <button type="submit" className="tt-btn primary" disabled={busy}>
        Add
      </button>
      <button type="button" className="tt-btn" onClick={() => setOpen(false)}>
        Cancel
      </button>
      {error ? (
        <span className="muted" role="alert">
          {error.message} {error.detail ?? ""}
        </span>
      ) : null}
    </form>
  );
}
