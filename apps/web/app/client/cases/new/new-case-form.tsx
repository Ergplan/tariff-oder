"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../../../components";
import { call } from "../../actions";

function shift(fy: string, n: number): string {
  const m = /^FY(\d{4})-\d{2}$/.exec(fy);
  if (!m) return "";
  const y = Number(m[1]) + n;
  return `FY${y}-${String((y + 1) % 100).padStart(2, "0")}`;
}

type Kind = "annual_arr" | "myt" | "true_up" | "apr";
const KIND_WORDS: Record<Kind, string> = { annual_arr: "ARR", myt: "MYT", true_up: "true-up", apr: "APR" };

export default function NewCaseForm({
  orgs,
  licensees,
  initialUtility,
}: {
  orgs: { id: string; name: string }[];
  licensees: { code: string; name: string; fixture: boolean }[];
  initialUtility: string;
}) {
  const router = useRouter();
  const [org, setOrg] = useState(orgs[0]?.id ?? "");
  const [utility, setUtility] = useState(initialUtility);
  const [kind, setKind] = useState<Kind>("annual_arr");
  const [base, setBase] = useState("FY2025-26");
  const [years, setYears] = useState(3);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const trueUp = kind === "true_up" || kind === "apr";
  const targets = trueUp ? [base] : kind === "annual_arr" ? [shift(base, 1)] : Array.from({ length: years }, (_, i) => shift(base, i + 1));
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError(null);
        const r = await call("cases", "POST", {
          organisation_id: org,
          utility_code: utility,
          title: title || `${utility} ${KIND_WORDS[kind]} ${targets[0]}${targets.length > 1 ? ` to ${targets[targets.length - 1]}` : ""}`,
          filing_kind: kind,
          base_fy: base,
          target_years: targets,
        });
        setBusy(false);
        if (!r.ok) return setError(r.error);
        router.push(`/client/cases/${(r.data as { id: string }).id}`);
      }}
    >
      <div className="form-grid">
        <label>
          Organisation
          <select value={org} onChange={(e) => setOrg(e.target.value)} required>
            {orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Licensee
          <select value={utility} onChange={(e) => setUtility(e.target.value)} required>
            <option value="">choose…</option>
            {licensees.map((l) => (
              <option key={l.code} value={l.code}>
                {l.code} — {l.name}
                {l.fixture ? " (FIXTURE)" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Filing
          <select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
            <option value="annual_arr">Annual ARR (next year)</option>
            <option value="myt">MYT control period</option>
            <option value="true_up">True-up of a past year (audited actuals)</option>
            <option value="apr">Annual performance review (running year)</option>
          </select>
        </label>
        <label>
          {trueUp ? "Year to true up" : "Base year"}
          <input value={base} onChange={(e) => setBase(e.target.value.trim())} pattern="FY\d{4}-\d{2}" required />
        </label>
        {kind === "myt" ? (
          <label>
            Control period (years)
            <input type="number" min={2} max={6} value={years} onChange={(e) => setYears(Number(e.target.value))} />
          </label>
        ) : null}
        <label>
          Title (optional)
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </label>
      </div>
      <p className="muted">
        {trueUp
          ? `The licensee's actuals of ${base} set against the Commission's reviewed approval of ${base}.`
          : `Target years: ${targets.filter(Boolean).join(", ") || "—"}`}
      </p>
      <button type="submit" disabled={busy || !org || !utility}>
        {busy ? "Creating…" : "Create the case"}
      </button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
