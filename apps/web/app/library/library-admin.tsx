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

type Proposal = {
  commission_code: string;
  url: string;
  title: string;
  document_kind: string | null;
  fiscal_year: string;
  utility_code: string | null;
  notes: string[];
  complete: boolean;
  decides?: { fy: string; value_type: string }[];
  variant?: string | null;
  preferred?: boolean;
  listing?: string | null;
};
type PageLine = { listing: string; fiscal_year: string; url: string; documents: number; error: string | null };

const key = (p: Proposal) => `${p.url}|${p.utility_code ?? ""}`;

/** Find documents on a commission's website: with its discovery profile (the library pages
 * through the listing by year by itself), or from one listing page (fetched or pasted).
 * Every proposal is a guess a person ticks before anything is recorded. */
export function DiscoverForm({ profiles = [] }: { profiles?: string[] }) {
  const router = useRouter();
  const [v, setV] = useState({ commission_code: "", page_url: "", page_html: "" });
  const [years, setYears] = useState("FY2024-25,FY2025-26,FY2026-27");
  const [busy, setBusy] = useState(false);
  const [props, setProps] = useState<Proposal[]>([]);
  const [pages, setPages] = useState<PageLine[]>([]);
  const [pick, setPick] = useState<Record<string, boolean>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const useProfile = profiles.includes(v.commission_code.toUpperCase());
  return (
    <>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          setMsg(null);
          setBusy(true);
          const r = useProfile
            ? await call("library/discover/profile", "POST", {
                commission_code: v.commission_code.toUpperCase(),
                fiscal_years: years.split(",").map((y) => y.trim()).filter(Boolean),
              })
            : await call("library/discover", "POST", { ...v, page_html: v.page_html.trim() ? v.page_html : null });
          setBusy(false);
          if (!r.ok) return setError(r.error);
          const list = useProfile ? (r.data as { proposals: Proposal[] }).proposals : (r.data as Proposal[]);
          setPages(useProfile ? (r.data as { pages: PageLine[] }).pages : []);
          setProps(list);
          setPick(Object.fromEntries(list.map((p) => [key(p), p.complete])));
        }}
      >
        <div className="form-grid">
          <label>
            Commission
            <input value={v.commission_code} onChange={(e) => setV({ ...v, commission_code: e.target.value.trim() })} required placeholder="UPERC" />
          </label>
          {useProfile ? (
            <label style={{ gridColumn: "span 2" }}>
              Financial years (the profile pages through each)
              <input value={years} onChange={(e) => setYears(e.target.value)} required />
            </label>
          ) : (
            <>
              <label style={{ gridColumn: "span 2" }}>
                Listing page URL
                <input value={v.page_url} onChange={(e) => setV({ ...v, page_url: e.target.value.trim() })} required type="url" />
              </label>
              <label style={{ gridColumn: "1 / -1" }}>
                Page source (optional: paste it when the list sits behind a search form)
                <textarea rows={3} value={v.page_html} onChange={(e) => setV({ ...v, page_html: e.target.value })} />
              </label>
            </>
          )}
        </div>
        <p className="muted">
          {useProfile
            ? `${v.commission_code.toUpperCase()} has a discovery profile: the library reads its listing pages year by year, one request at a time.`
            : `Commissions with a discovery profile: ${profiles.join(", ") || "none yet"}. For the others give a listing page.`}
        </p>
        <button type="submit" disabled={busy}>
          {busy ? "Reading the commission's website…" : "Find documents"}
        </button>
      </form>
      {error ? <ErrorBanner error={error} /> : null}
      {pages.length ? (
        <ul className="muted">
          {pages.map((pg, i) => (
            <li key={i}>
              {pg.listing} {pg.fiscal_year}: {pg.error ? <span className="badge" data-tone="bad">{pg.error}</span> : `${pg.documents} documents`}
            </li>
          ))}
        </ul>
      ) : null}
      {props.length ? (
        <>
          <p className="muted">
            {props.length} proposals, {props.filter((p) => p.complete).length} complete. Guesses only: tick the right ones. A scanned copy is unticked when a text or digitally signed copy is
            listed beside it.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th />
                  <th>Title</th>
                  <th>Kind</th>
                  <th>Year</th>
                  <th>Licensee</th>
                  <th>Decides</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {props.map((p) => (
                  <tr key={key(p)} style={p.preferred === false ? { opacity: 0.6 } : undefined}>
                    <td>
                      <input type="checkbox" checked={!!pick[key(p)]} disabled={!p.document_kind} onChange={(e) => setPick({ ...pick, [key(p)]: e.target.checked })} />
                    </td>
                    <td>
                      <a href={p.url} target="_blank" rel="noreferrer noopener">
                        {p.title}
                      </a>
                      {p.variant ? <span className="badge" data-tone="neutral">{p.variant.replace("_", " ")}</span> : null}
                      {p.listing ? <div className="muted">{p.listing}</div> : null}
                    </td>
                    <td>{p.document_kind ?? "?"}</td>
                    <td className="mono">{p.fiscal_year || "—"}</td>
                    <td>{p.utility_code ?? "—"}</td>
                    <td className="muted mono">{(p.decides ?? []).map((d) => `${d.fy} ${d.value_type}`).join(", ")}</td>
                    <td className="muted">{p.notes.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            type="button"
            onClick={async () => {
              const chosen = props.filter((p) => pick[key(p)] && p.document_kind);
              const r = await call(
                "library/entries/bulk",
                "POST",
                chosen.map((p) => ({ commission_code: p.commission_code, utility_code: p.utility_code, document_kind: p.document_kind, fiscal_year: p.fiscal_year, title: p.title, url: p.url })),
              );
              if (!r.ok) return setError(r.error);
              setMsg(`${chosen.length} entries recorded as located; acquire them from the list below.`);
              router.refresh();
            }}
          >
            Record selected
          </button>
          {msg ? <p className="muted">{msg}</p> : null}
        </>
      ) : null}
    </>
  );
}
