"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse } from "@tariff/contracts";
import { ErrorBanner } from "../components";
import { call } from "../client/actions";

const KINDS = ["tariff_order", "arr_true_up_order", "myt_order", "mid_term_review", "arr_petition", "myt_petition", "regulation", "regulation_amendment"];

/** Seed expected slots for some years; record an official URL for a document. */
export function SeedForm() {
  const router = useRouter();
  const [years, setYears] = useState("FY2024-25,FY2025-26,FY2026-27");
  const [codes, setCodes] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        const r = await call("library/seed", "POST", {
          fiscal_years: years.split(",").map((y) => y.trim()).filter(Boolean),
          commission_codes: codes.trim() ? codes.split(",").map((c) => c.trim()) : null,
        });
        if (!r.ok) return setError(r.error);
        const d = r.data as { created: number; existing: number; linked: number };
        setMsg(`${d.created} expected slots created, ${d.existing} already there, ${d.linked} registered orders linked.`);
        router.refresh();
      }}
    >
      <div className="form-grid">
        <label>
          Fiscal years (comma separated)
          <input value={years} onChange={(e) => setYears(e.target.value)} required />
        </label>
        <label>
          Commissions (blank = all)
          <input value={codes} onChange={(e) => setCodes(e.target.value)} placeholder="UPERC,KERC" />
        </label>
      </div>
      <button type="submit">Seed expected documents</button>
      {msg ? <p className="muted">{msg}</p> : null}
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}

export function EntryForm() {
  const router = useRouter();
  const [v, setV] = useState({ commission_code: "", utility_code: "", document_kind: "tariff_order", fiscal_year: "", title: "", url: "" });
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [acquire, setAcquire] = useState(true);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        const r = await call("library/entries", "PUT", { ...v, utility_code: v.utility_code || null, title: v.title || null });
        if (!r.ok) return setError(r.error);
        if (acquire) {
          const a = await call(`library/entries/${(r.data as { id: string }).id}/acquire`, "POST");
          if (!a.ok) return setError(a.error);
        }
        router.refresh();
      }}
    >
      <div className="form-grid">
        <label>
          Commission
          <input value={v.commission_code} onChange={(e) => setV({ ...v, commission_code: e.target.value.trim() })} required placeholder="UPERC" />
        </label>
        <label>
          Licensee (blank for a regulation)
          <input value={v.utility_code} onChange={(e) => setV({ ...v, utility_code: e.target.value.trim() })} placeholder="NPCL" />
        </label>
        <label>
          Kind
          <select value={v.document_kind} onChange={(e) => setV({ ...v, document_kind: e.target.value })}>
            {KINDS.map((k) => (
              <option key={k}>{k}</option>
            ))}
          </select>
        </label>
        <label>
          Year (blank = current control period)
          <input value={v.fiscal_year} onChange={(e) => setV({ ...v, fiscal_year: e.target.value.trim() })} placeholder="FY2026-27" />
        </label>
        <label>
          Title
          <input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />
        </label>
        <label style={{ gridColumn: "span 2" }}>
          Official URL (the commission&apos;s own website)
          <input value={v.url} onChange={(e) => setV({ ...v, url: e.target.value.trim() })} required type="url" />
        </label>
        <label>
          <span>
            <input type="checkbox" checked={acquire} onChange={(e) => setAcquire(e.target.checked)} /> acquire now
          </span>
        </label>
      </div>
      <button type="submit">Record the document</button>
      {error ? <ErrorBanner error={error} /> : null}
    </form>
  );
}
