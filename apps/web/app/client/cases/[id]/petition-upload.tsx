"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";
import { ErrorBanner } from "../../../components";

/** Upload the petition's inputs workbook (XLSX laid out as the filed formats).  The API checks
 * it and compares it with the filed inputs; nothing is filled until someone asks. */
export default function PetitionUpload({ caseId }: { caseId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", margin: "8px 0 12px" }}
      onSubmit={async (e) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        const file = form.get("file");
        if (!(file instanceof File) || !file.size) return;
        setBusy(true);
        setError(null);
        try {
          const res = await fetch(`/api/client/cases/${encodeURIComponent(caseId)}/petition/workbooks`, { method: "POST", body: form });
          if (!res.ok) setError(await readError(res));
          else {
            (e.target as HTMLFormElement).reset();
            router.refresh();
          }
        } catch {
          setError(networkError("The upload"));
        }
        setBusy(false);
      }}
    >
      <label style={{ maxWidth: "100%" }}>
        Inputs workbook (.xlsx){" "}
        <input type="file" name="file" style={{ maxWidth: "100%" }} accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" required />
      </label>
      <button type="submit" disabled={busy} data-tone="primary">
        {busy ? "Checking the workbook…" : "Upload"}
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
