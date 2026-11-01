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
  const lic = licensees.find((l) => l.code === utility);
  const KINDS: { k: Kind; t: string; d: string }[] = [
    { k: "annual_arr", t: "Annual ARR", d: "The next year's revenue requirement and tariff." },
    { k: "myt", t: "MYT control period", d: "Every year of a multi-year control period." },
    { k: "true_up", t: "True-up", d: "A past year's audited actuals against the approval." },
    { k: "apr", t: "APR", d: "The running year's performance review." },
  ];
  return (
    <form
      className="split"
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
      <div>
        <p className="eyebrow">
          <span className="dot" aria-hidden="true" />
          01 · The filing
        </p>
        <div className="choice" role="radiogroup" aria-label="Filing">
          {KINDS.map((x) => (
            <label key={x.k} data-on={kind === x.k}>
              <input type="radio" name="kind" value={x.k} checked={kind === x.k} onChange={() => setKind(x.k)} />
              <span className="t">{x.t}</span>
              <span className="d">{x.d}</span>
            </label>
          ))}
        </div>
        <p className="eyebrow" style={{ marginTop: "2rem" }}>
          <span className="dot" aria-hidden="true" />
          02 · Licensee and years
        </p>
        <div className="fields">
          <label className="field">
            Organisation
            <select value={org} onChange={(e) => setOrg(e.target.value)} required>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
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
          <label className="field">
            {trueUp ? "Year to true up" : "Base year"}
            <input value={base} onChange={(e) => setBase(e.target.value.trim())} pattern="FY\d{4}-\d{2}" required />
          </label>
          {kind === "myt" ? (
            <label className="field">
              Control period (years)
              <input type="number" min={2} max={6} value={years} onChange={(e) => setYears(Number(e.target.value))} />
            </label>
          ) : null}
          <label className="field" style={{ gridColumn: "1 / -1" }}>
            Title (optional)
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder={`${utility || "LICENSEE"} ${KIND_WORDS[kind]} ${targets[0] ?? ""}`} />
          </label>
        </div>
        {error ? <ErrorBanner error={error} /> : null}
      </div>
      <aside className="summary-card" aria-label="What will be created">
        <p className="eyebrow">
          <span className="dot" aria-hidden="true" />
          The petition
        </p>
        <div className="petition" style={{ padding: 0, minHeight: 0, background: "transparent" }}>
          <span className="code">{utility || "—"}</span>
          <span className="title">{lic ? lic.name : "Choose the licensee"}</span>
        </div>
        <dl>
          <dt>Filing</dt>
          <dd>{KINDS.find((x) => x.k === kind)?.t}</dd>
          <dt>{trueUp ? "Year" : "Base year"}</dt>
          <dd className="mono">{base}</dd>
          <dt>{trueUp ? "Sets" : "Targets"}</dt>
          <dd>
            {trueUp ? (
              <span className="muted">the licensee&apos;s actuals of {base} against the Commission&apos;s reviewed approval of {base}</span>
            ) : (
              <span className="chips">
                {targets.filter(Boolean).map((t) => (
                  <span key={t} className="chip">
                    {t}
                  </span>
                ))}
              </span>
            )}
          </dd>
        </dl>
        <p className="muted" style={{ fontSize: "0.85rem" }}>
          The base year is the last year with reviewed figures: its final true-up, else its approval. The studio shows what is ready and what is missing once the petition is created.
        </p>
        <button type="submit" disabled={busy || !org || !utility} style={{ width: "100%" }}>
          {busy ? "Creating…" : "Create the petition →"}
        </button>
      </aside>
    </form>
  );
}
