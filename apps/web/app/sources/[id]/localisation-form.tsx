"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { ErrorResponse, LocalisationOut, LocalisationRegionOut } from "@tariff/contracts";
import { networkError, readError } from "@/lib/client-errors";

const ROLES = [
  "approved_schedule",
  "approved_summary",
  "existing_tariff",
  "proposed_tariff",
  "amendment_diff",
  "formula_parameters",
  "network_charges",
  "loss_trajectory",
  "green_tariff",
  "illustrative",
  "derived_not_tariff",
  "other",
] as const;

type Edit = { role: string; sub_role: string; page_start: number; page_end: number; utility: string; period: string; note: string };

function fromRegion(r: LocalisationRegionOut): Edit {
  return {
    role: r.role,
    sub_role: r.sub_role ?? "",
    page_start: r.page_start,
    page_end: r.page_end,
    utility: r.utility ?? "",
    period: r.period ?? "",
    note: r.note ?? "",
  };
}

/**
 * The localisation checkpoint (Section 6.5).  A reviewer confirms the detected regions or
 * corrects them; both need a rationale and an explicit statement that the pages were looked
 * at.  Confirming an ambiguous record is refused by the API; the form only offers correction
 * then.  Nothing is shown as decided until the API says so.
 */
export function LocalisationForm({ sourceId, record }: { sourceId: string; record: LocalisationOut }) {
  const router = useRouter();
  const ambiguous = record.status === "ambiguous";
  const [mode, setMode] = useState<"confirm" | "correct">(ambiguous ? "correct" : "confirm");
  const [rationale, setRationale] = useState("");
  const [viewed, setViewed] = useState(false);
  const [regions, setRegions] = useState<Edit[]>(record.regions.map(fromRegion));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorResponse | null>(null);
  const [done, setDone] = useState<LocalisationOut | null>(null);
  const [attempted, setAttempted] = useState(false);
  const problems: string[] = [];
  if (!viewed) problems.push("tick the box confirming you opened the pages");
  if (rationale.trim().length < 5) problems.push("write a rationale of at least five characters");
  if (mode === "correct" && regions.length === 0) problems.push("keep at least one region");

  function update(i: number, patch: Partial<Edit>) {
    setRegions((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setAttempted(true);
    if (busy || problems.length) return;
    setBusy(true);
    setError(null);
    const body = {
      decision: mode,
      rationale,
      pages_viewed: viewed,
      expected_version: record.version,
      regions:
        mode === "correct"
          ? regions.map((r) => ({
              role: r.role,
              sub_role: r.sub_role || null,
              page_start: Number(r.page_start),
              page_end: Number(r.page_end),
              utility: r.utility || null,
              period: r.period || null,
              note: r.note || null,
            }))
          : null,
    };
    try {
      const res = await fetch(`/api/sources/${sourceId}/localisation`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await readError(res);
        console.error("localisation decision failed", err);
        setError(err);
      } else {
        setDone((await res.json()) as LocalisationOut);
        router.refresh();
      }
    } catch (e) {
      console.error("localisation decision failed", e);
      setError(networkError("The decision"));
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="banner" data-tone="ok">
        Localisation {done.status} by {done.decided_by}. Extraction may proceed from the confirmed regions.
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="card" aria-label="Localisation decision">
      <div className="label">Reviewer decision</div>
      {ambiguous ? (
        <p className="muted">
          The rules could not localise the approved schedule unambiguously, so confirming is not offered: correct the regions
          below, keeping exactly one <code>approved_schedule</code> region per period.
        </p>
      ) : (
        <p>
          <label>
            <input type="radio" name="mode" checked={mode === "confirm"} onChange={() => setMode("confirm")} /> Confirm the
            detected regions
          </label>{" "}
          <label>
            <input type="radio" name="mode" checked={mode === "correct"} onChange={() => setMode("correct")} /> Correct them
          </label>
        </p>
      )}
      {mode === "correct" ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Role</th>
                <th>Sub-role</th>
                <th>From</th>
                <th>To</th>
                <th>Utility</th>
                <th>Period</th>
                <th>Note</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {regions.map((r, i) => (
                <tr key={i}>
                  <td>
                    <select value={r.role} onChange={(e) => update(i, { role: e.target.value })} aria-label="role">
                      {ROLES.map((x) => (
                        <option key={x} value={x}>
                          {x}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input value={r.sub_role} onChange={(e) => update(i, { sub_role: e.target.value })} size={14} aria-label="sub-role" />
                  </td>
                  <td>
                    <input type="number" min={1} value={r.page_start} onChange={(e) => update(i, { page_start: Number(e.target.value) })} size={4} aria-label="from page" />
                  </td>
                  <td>
                    <input type="number" min={1} value={r.page_end} onChange={(e) => update(i, { page_end: Number(e.target.value) })} size={4} aria-label="to page" />
                  </td>
                  <td>
                    <input value={r.utility} onChange={(e) => update(i, { utility: e.target.value })} size={8} aria-label="utility" />
                  </td>
                  <td>
                    <input value={r.period} onChange={(e) => update(i, { period: e.target.value })} size={10} aria-label="period" />
                  </td>
                  <td>
                    <input value={r.note} onChange={(e) => update(i, { note: e.target.value })} size={20} aria-label="note" />
                  </td>
                  <td>
                    <button type="button" onClick={() => setRegions((rs) => rs.filter((_, j) => j !== i))} aria-label="remove region">
                      remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            onClick={() => setRegions((rs) => [...rs, { role: "approved_schedule", sub_role: "", page_start: 1, page_end: 1, utility: "", period: "", note: "" }])}
          >
            add region
          </button>
        </div>
      ) : null}
      <p>
        <label>
          Rationale{" "}
          <input value={rationale} onChange={(e) => setRationale(e.target.value)} required minLength={5} size={60} placeholder="what you checked and why this is the approved schedule" />
        </label>
      </p>
      <p>
        <label>
          <input type="checkbox" checked={viewed} onChange={(e) => setViewed(e.target.checked)} required /> I opened the pages in the
          region list and checked the cues against the document
        </label>
      </p>
      {error ? (
        <div className="banner" data-tone="bad" role="alert">
          <strong>{error.error_type}</strong>: {error.message} {error.detail ? <em>{error.detail}</em> : null} — {error.next_step}
          {error.request_id ? (
            <div className="muted">
              request id <code>{error.request_id}</code>
            </div>
          ) : null}
        </div>
      ) : null}
      <button type="submit" disabled={busy} aria-describedby="decision-requirements">
        {busy ? "Recording…" : mode === "confirm" ? "Confirm localisation" : "Record corrected regions"}
      </button>
      <div id="decision-requirements" className={attempted && problems.length ? "banner" : "muted"} data-tone="warn" role={attempted && problems.length ? "alert" : undefined}>
        {problems.length ? `Before this can be recorded: ${problems.join("; ")}.` : "Ready to record. The decision is written under your name with the rules and profile versions."}
      </div>
    </form>
  );
}
