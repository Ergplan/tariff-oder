import Link from "next/link";
import { apiTry } from "@/lib/api";
import { ErrorBanner } from "../../components";
import { Eyebrow, Journey, SectionHead } from "../studio";
import { type Atlas, STATUS_WORDS, TILES, status } from "./data";

export const dynamic = "force-dynamic";

const JOURNEY_STEPS = [
  { t: "India", d: "Pick a state on the map or from the list." },
  { t: "State", d: "Its commission, the regulations on file and every distribution licensee." },
  { t: "Discom", d: "Its reviewed ARR history, each figure with its order and page, and its documents." },
  { t: "Norms", d: "How the commission's regulations form each ARR line, and the norms its orders applied." },
  { t: "Petition", d: "Start one: setup, data, formulate, freeze, draft. A person edits and files it." },
];

/**
 * The atlas (increment 52): the way in.  India as a tile map — one tile per state or union
 * territory, in its approximate place — coloured by what is on record: reviewed ARR facts,
 * orders being read, documents located, or nothing yet.  A click opens the state.
 */
export default async function AtlasPage() {
  const res = await apiTry<Atlas>("/atlas");
  if (res.error || !res.data) return <ErrorBanner error={res.error!} />;
  const states = res.data.states.filter((s) => !s.fixture || s.reviewed_facts > 0 || s.orders_reading > 0);
  const byCode = Object.fromEntries(states.map((s) => [s.code, s]));
  const placed = Object.entries(TILES).filter(([code]) => byCode[code]);
  const totals = states.reduce(
    (a, s) => ({ facts: a.facts + s.reviewed_facts, reading: a.reading + s.orders_reading, lic: a.lic + s.licensees, docs: a.docs + s.documents_located }),
    { facts: 0, reading: 0, lic: 0, docs: 0 },
  );
  return (
    <>
      <Journey steps={[{ label: "India" }]} />
      <header className="case-head" style={{ paddingTop: 0 }}>
        <Eyebrow>Atlas · {states.length} states and union territories</Eyebrow>
        <h1>Choose a state.</h1>
        <p className="muted" style={{ margin: 0, maxWidth: "44rem", fontSize: "1.02rem" }}>
          Every state&apos;s commission, its distribution licensees, their regulatory record and the commission&apos;s ARR norms — then the petition, prepared step by step.
        </p>
      </header>

      <div className="statline">
        <div>
          <div className="num">{totals.lic}</div>
          <div className="cap">Licensees</div>
        </div>
        <div>
          <div className="num">{totals.docs}</div>
          <div className="cap">Documents located</div>
        </div>
        <div>
          <div className="num">{totals.reading}</div>
          <div className="cap">Orders being read</div>
        </div>
        <div>
          <div className="num">{totals.facts}</div>
          <div className="cap">Reviewed ARR facts</div>
        </div>
      </div>

      <div className="atlas">
        <div>
          <div className="tilemap" role="list" aria-label="Map of India by state">
            {Array.from({ length: 7 }, (_, row) =>
              Array.from({ length: 9 }, (_, col) => {
                const hit = placed.find(([, [c, r]]) => c === col && r === row);
                if (!hit) return <span key={`${col}-${row}`} className="gap" aria-hidden="true" />;
                const [code, [, , short]] = hit;
                const s = byCode[code];
                const st = status(s);
                return (
                  <Link
                    key={code}
                    role="listitem"
                    href={`/client/states/${encodeURIComponent(code)}`}
                    className="tile"
                    data-status={st}
                    data-fixture={s.fixture}
                    title={`${s.name} — ${s.commissions.map((c) => c.code).join(", ")} · ${STATUS_WORDS[st]}`}
                    aria-label={`${s.name}: ${STATUS_WORDS[st]}`}
                  >
                    <span className="ab">{short}</span>
                    <span className="n">{s.licensees ? `${s.licensees} lic.` : "—"}</span>
                  </Link>
                );
              }),
            )}
          </div>
          <div className="legend">
            {(["facts", "reading", "located", "none"] as const).map((k) => (
              <span key={k}>
                <i
                  style={{
                    background: { facts: "var(--accent)", reading: "var(--accent-soft)", located: "var(--info-bg)", none: "transparent" }[k],
                    border: `1px ${k === "none" ? "dashed" : "solid"} ${k === "facts" || k === "reading" ? "var(--accent)" : k === "located" ? "var(--info-line)" : "var(--line-strong)"}`,
                  }}
                />
                {STATUS_WORDS[k]}
              </span>
            ))}
          </div>
          <p className="muted" style={{ fontSize: "0.78rem", marginTop: "0.8rem" }}>
            A tile map: each state or union territory is one equal tile in its approximate place. It is not a map of boundaries.
          </p>
        </div>

        <div>
          <SectionHead title="States" aside={`${states.length} · by name`} />
          <ul className="statelist">
            {states.map((s) => (
              <li key={s.code}>
                <Link href={`/client/states/${encodeURIComponent(s.code)}`}>
                  <span className="ab">{TILES[s.code]?.[2] ?? s.code}</span>
                  <span>
                    <span className="nm">{s.name}</span>
                    <span className="cm">
                      {s.commissions.map((c) => c.code).join(" · ")}
                      {s.fixture ? " · fixture" : ""}
                    </span>
                  </span>
                  <span className="ct">
                    <b>{s.licensees}</b> lic · <b>{s.documents_located}</b>/{s.documents} docs
                    {s.reviewed_facts ? (
                      <>
                        {" "}
                        · <b>{s.reviewed_facts}</b> facts
                      </>
                    ) : null}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <SectionHead num="→" title="From the map to a petition" aside="five stops" />
      <div className="flow">
        {JOURNEY_STEPS.map((f, i) => (
          <div key={f.t}>
            <span className="n">{String(i + 1).padStart(2, "0")}</span>
            <h3>{f.t}</h3>
            <p>{f.d}</p>
          </div>
        ))}
      </div>
      <p className="muted" style={{ fontSize: "0.82rem", marginTop: "1.4rem" }}>
        {res.data.note}
      </p>
    </>
  );
}
