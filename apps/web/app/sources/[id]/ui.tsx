import type { ReactNode } from "react";

/** "402–417, 419–423" instead of twenty-two numbers.  Pure presentation; nothing is dropped. */
export function ranges(nums: number[]): string {
  const xs = [...new Set(nums)].sort((a, b) => a - b);
  const out: string[] = [];
  let i = 0;
  while (i < xs.length) {
    let j = i;
    while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j++;
    out.push(j > i + 1 ? `${xs[i]}–${xs[j]}` : j === i + 1 ? `${xs[i]}, ${xs[j]}` : `${xs[i]}`);
    i = j + 1;
  }
  return out.join(", ");
}

/** A list of page numbers: count first, the ranges on demand once the list is long. */
export function PageList({ pages, label, tone = "warn", inline = 12 }: { pages: number[]; label: string; tone?: string; inline?: number }) {
  if (!pages.length) return <span className="muted">none</span>;
  const text = ranges(pages);
  if (pages.length <= inline) {
    return (
      <>
        <span className="badge" data-tone={tone}>
          {pages.length} {label}
        </span>{" "}
        <span className="mono">{text}</span>
      </>
    );
  }
  return (
    <details className="inline">
      <summary>
        <span className="badge" data-tone={tone}>
          {pages.length} {label}
        </span>{" "}
        <span className="muted">show pages</span>
      </summary>
      <span className="mono">{text}</span>
    </details>
  );
}

/** A collapsible section with a one-line summary readable while closed. */
export function Section({
  id,
  title,
  summary,
  open = false,
  children,
}: {
  id: string;
  title: string;
  summary?: ReactNode;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="section" id={id} open={open}>
      <summary>
        <span className="title">{title}</span>
        {summary ? <span className="summary muted">{summary}</span> : null}
      </summary>
      <div className="body">{children}</div>
    </details>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="stat" data-tone={tone}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}
