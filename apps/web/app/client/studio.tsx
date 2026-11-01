import Link from "next/link";

/** Shared pieces of the Petition Studio (increment 51): the client application's own surfaces. */

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="eyebrow">
      <span className="dot" aria-hidden="true" />
      {children}
    </p>
  );
}

export function SectionHead({ num, title, aside }: { num?: string; title: string; aside?: React.ReactNode }) {
  return (
    <div className="sec-head">
      <h2>
        {num ? <span className="num">{num}</span> : null}
        {title}
      </h2>
      {aside ? <span className="aside">{aside}</span> : null}
    </div>
  );
}

export function Panel({ num, title, aside, children, id }: { num?: string; title: string; aside?: React.ReactNode; children: React.ReactNode; id?: string }) {
  return (
    <section className="panel" id={id}>
      <div className="ph">
        <h2>
          {num ? <span className="num">{num}</span> : null}
          {title}
        </h2>
        {aside ? <span className="muted">{aside}</span> : null}
      </div>
      <div className="pb">{children}</div>
    </section>
  );
}

export function Stepper({ steps, current }: { steps: { key: string; label: string }[]; current: string }) {
  const idx = steps.findIndex((s) => s.key === current);
  return (
    <ol className="stepper" aria-label="Petition steps" style={{ ["--n" as string]: steps.length }}>
      {steps.map((s, i) => (
        <li key={s.key} data-done={i < idx} data-current={i === idx} aria-current={i === idx ? "step" : undefined}>
          <span className="k">{String(i + 1).padStart(2, "0")}</span>
          <span className="t">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export function SegBar({ steps, current }: { steps: number; current: number }) {
  return (
    <div className="segbar" style={{ ["--n" as string]: steps }} aria-label={`step ${current + 1} of ${steps}`}>
      {Array.from({ length: steps }, (_, i) => (
        <span key={i} data-done={i < current} data-current={i === current} />
      ))}
    </div>
  );
}

export function NextAction({ what, why, href, label }: { what: string; why?: string; href?: string; label?: string }) {
  return (
    <div className="next-action" role="status">
      <div>
        <div className="eyebrow" style={{ margin: 0 }}>
          Next
        </div>
        <div className="what">{what}</div>
        {why ? <div className="why">{why}</div> : null}
      </div>
      {href ? (
        <Link className="btn primary" href={href}>
          {label ?? "Go"} <span className="arrow">→</span>
        </Link>
      ) : null}
    </div>
  );
}

/** The five steps of an ARR or MYT petition, and of a true-up or APR filing. */
export const ARR_STEPS = [
  { key: "setup", label: "Setup" },
  { key: "assumptions", label: "Data & assumptions" },
  { key: "formulated", label: "Formulate" },
  { key: "frozen", label: "Freeze" },
  { key: "drafted", label: "Draft petition" },
];
export const TRUE_UP_STEPS = [
  { key: "setup", label: "Setup" },
  { key: "assumptions", label: "Actuals" },
  { key: "formulated", label: "Statement" },
  { key: "frozen", label: "Freeze" },
  { key: "drafted", label: "Draft petition" },
];

export const FILING_WORDS: Record<string, string> = {
  annual_arr: "Annual ARR",
  myt: "MYT control period",
  true_up: "True-up",
  apr: "Annual performance review",
};

/** Where the user is on the way from the map of India to a petition (increment 52). */
export function Journey({ steps }: { steps: { label: string; href?: string }[] }) {
  return (
    <nav aria-label="Journey">
      <ol className="journey">
        {steps.map((s, i) => {
          const last = i === steps.length - 1;
          return (
            <li key={`${s.label}-${i}`} aria-current={last ? "step" : undefined}>
              {s.href && !last ? <Link href={s.href}>{s.label}</Link> : <span>{s.label}</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
