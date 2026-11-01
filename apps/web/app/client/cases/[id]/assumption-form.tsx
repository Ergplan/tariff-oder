"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../actions";

function guessUnit(key: string): string {
  if (key.endsWith("_pct") || key.endsWith("_PCT")) return "percent";
  if (key.includes("inr_per_kwh")) return "INR_per_kWh";
  if (key.startsWith("E.")) return "MU";
  return "INR_crore";
}

/** Add an assumption to a case: a value a named person enters with a rationale, or a
 * regulation parameter grounded on the clause that prints it. */
export default function AssumptionForm({ caseId, keys, years }: { caseId: string; keys: string[]; years: string[] }) {
  const router = useRouter();
  const [key, setKey] = useState(keys[0] ?? "");
  const [fy, setFy] = useState("");
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState(guessUnit(keys[0] ?? ""));
  const [kind, setKind] = useState<"user" | "regulation_clause">("user");
  const [rationale, setRationale] = useState("");
  const [clause, setClause] = useState({ source_id: "", page_index: "", citation: "", excerpt: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const r = await call(`cases/${caseId}/assumptions`, "POST", {
          key,
          fiscal_year: fy,
          value,
          unit,
          source_kind: kind,
          rationale,
          clause_ref: kind === "regulation_clause" ? { ...clause, page_index: Number(clause.page_index) } : null,
        });
        setBusy(false);
        if (!r.ok) return setError(r.error);
        setValue("");
        setRationale("");
        router.refresh();
      }}
    >
      <div className="form-grid">
        <label>
          Key
          <input
            list="assumption-keys"
            value={key}
            onChange={(e) => {
              setKey(e.target.value);
              setUnit(guessUnit(e.target.value));
            }}
            required
          />
          <datalist id="assumption-keys">
            {keys.map((k) => (
              <option key={k} value={k} />
            ))}
          </datalist>
        </label>
        <label>
          Year
          <select value={fy} onChange={(e) => setFy(e.target.value)}>
            <option value="">every year</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label>
          Value
          <input value={value} onChange={(e) => setValue(e.target.value.trim())} inputMode="decimal" required />
        </label>
        <label>
          Unit
          <select value={unit} onChange={(e) => setUnit(e.target.value)}>
            {["INR_crore", "MU", "percent", "INR_per_kWh", "MW"].map((u) => (
              <option key={u}>{u}</option>
            ))}
          </select>
        </label>
        <label>
          Source
          <select value={kind} onChange={(e) => setKind(e.target.value as "user" | "regulation_clause")}>
            <option value="user">my assumption</option>
            <option value="regulation_clause">a regulation clause</option>
          </select>
        </label>
        <label style={{ gridColumn: "span 2" }}>
          Rationale (required)
          <input value={rationale} onChange={(e) => setRationale(e.target.value)} required />
        </label>
      </div>
      {kind === "regulation_clause" ? (
        <div className="form-grid">
          <label>
            Regulation source id
            <input value={clause.source_id} onChange={(e) => setClause({ ...clause, source_id: e.target.value.trim() })} required />
          </label>
          <label>
            Page
            <input value={clause.page_index} onChange={(e) => setClause({ ...clause, page_index: e.target.value })} inputMode="numeric" required />
          </label>
          <label>
            Citation
            <input value={clause.citation} onChange={(e) => setClause({ ...clause, citation: e.target.value })} placeholder="Regulation 23(1)" />
          </label>
          <label style={{ gridColumn: "span 2" }}>
            Exact excerpt (must be on that page and print the value)
            <input value={clause.excerpt} onChange={(e) => setClause({ ...clause, excerpt: e.target.value })} required />
          </label>
        </div>
      ) : null}
      <button type="submit" disabled={busy}>
        {busy ? "Adding…" : "Add assumption"}
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
