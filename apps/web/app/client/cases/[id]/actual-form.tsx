"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../actions";

type Source = "document" | "statement" | "fact" | "estimate";
const UNITS = ["INR_crore", "INR_lakh", "INR_million", "MU", "percent", "INR_per_kWh", "paise_per_kWh", "MW"];

/** Enter one actual with its source.  A document actual is checked on the page (the excerpt
 * must be there and print the value); a statement names a document the application cannot
 * see and stays labelled unchecked; an estimate is for an APR only. */
export default function ActualForm({
  caseId,
  kind,
  lines,
  documents,
}: {
  caseId: string;
  kind: string;
  lines: { code: string; label: string; unit: string }[];
  documents: { id: string; label: string }[];
}) {
  const router = useRouter();
  const [line, setLine] = useState(lines[0]?.code ?? "");
  const [source, setSource] = useState<Source>(documents.length ? "document" : "statement");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState(lines[0]?.unit || "INR_crore");
  const [doc, setDoc] = useState(documents[0]?.id ?? "");
  const [page, setPage] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [docName, setDocName] = useState("");
  const [factId, setFactId] = useState("");
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const body: Record<string, unknown> = { line_code: line, source_kind: source, rationale: rationale || null };
        if (source === "fact") body.fact_id = factId;
        else {
          body.stated_value = value;
          body.stated_unit = unit;
        }
        if (source === "document") Object.assign(body, { source_id: doc, page_index: Number(page), excerpt });
        if (source === "statement" || source === "estimate") Object.assign(body, { document_name: docName, page_index: page ? Number(page) : null });
        const r = await call(`cases/${caseId}/actuals`, "POST", body);
        setBusy(false);
        if (!r.ok) return setError(r.error);
        setValue("");
        setExcerpt("");
        setRationale("");
        router.refresh();
      }}
    >
      <div className="form-grid">
        <label>
          Line
          <input
            list="actual-lines"
            value={line}
            onChange={(e) => {
              setLine(e.target.value.trim());
              const l = lines.find((x) => x.code === e.target.value.trim());
              if (l?.unit) setUnit(l.unit);
            }}
            required
          />
          <datalist id="actual-lines">
            {lines.map((l) => (
              <option key={l.code} value={l.code}>
                {l.label}
              </option>
            ))}
          </datalist>
        </label>
        <label>
          Source
          <select value={source} onChange={(e) => setSource(e.target.value as Source)}>
            <option value="document">A page of a registered document (checked)</option>
            <option value="statement">A document the application cannot see (unchecked)</option>
            <option value="fact">A reviewed fact of voice actual</option>
            {kind === "apr" ? <option value="estimate">An estimate for the rest of the year</option> : null}
          </select>
        </label>
        {source === "fact" ? (
          <label>
            Fact id
            <input value={factId} onChange={(e) => setFactId(e.target.value.trim())} required />
          </label>
        ) : (
          <>
            <label>
              Value as written
              <input value={value} onChange={(e) => setValue(e.target.value)} inputMode="decimal" required />
            </label>
            <label>
              Unit as written
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                {UNITS.map((u) => (
                  <option key={u}>{u}</option>
                ))}
              </select>
            </label>
          </>
        )}
        {source === "document" ? (
          <>
            <label>
              Document
              <input list="actual-docs" value={doc} onChange={(e) => setDoc(e.target.value.trim())} placeholder="source id" required />
              <datalist id="actual-docs">
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </datalist>
            </label>
            <label>
              Page
              <input type="number" min={1} value={page} onChange={(e) => setPage(e.target.value)} required />
            </label>
            <label className="wide">
              Excerpt (copied from the page, printing the value)
              <input value={excerpt} onChange={(e) => setExcerpt(e.target.value)} maxLength={600} required />
            </label>
          </>
        ) : null}
        {source === "statement" || source === "estimate" ? (
          <>
            <label>
              Document it rests on
              <input value={docName} onChange={(e) => setDocName(e.target.value)} maxLength={300} required />
            </label>
            <label>
              Page (optional)
              <input type="number" min={1} value={page} onChange={(e) => setPage(e.target.value)} />
            </label>
          </>
        ) : null}
        <label className="wide">
          Rationale{source === "statement" || source === "estimate" ? "" : " (optional)"}
          <input value={rationale} onChange={(e) => setRationale(e.target.value)} maxLength={2000} required={source === "statement" || source === "estimate"} />
        </label>
      </div>
      <button type="submit" disabled={busy || !line}>
        {busy ? "Adding…" : "Add the actual"}
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
