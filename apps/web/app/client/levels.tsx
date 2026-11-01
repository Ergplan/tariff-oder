/** Reading levels of a library document (ADR-0019), from "missing" to "published". */
export const LEVELS = ["missing", "located", "failed", "acquired", "read", "reviewed", "published"] as const;

export const LEVEL_HELP: Record<string, string> = {
  missing: "expected, not yet located: no official URL recorded",
  located: "official URL recorded, not yet fetched",
  failed: "the last fetch failed (see the entry)",
  acquired: "registered as a source, not yet read",
  read: "read by the pipeline; readings await review",
  reviewed: "a reviewer has decided readings of it",
  published: "reviewed facts from it are published",
};

export const KIND_SHORT: Record<string, string> = {
  tariff_order: "Tariff order",
  arr_true_up_order: "True-up order",
  myt_order: "MYT order",
  mid_term_review: "Mid-term review",
  arr_petition: "ARR petition",
  myt_petition: "MYT petition",
  regulation: "Regulations",
  regulation_amendment: "Amendment",
};

export function Level({ level }: { level: string }) {
  return (
    <span className="level" data-level={level} title={LEVEL_HELP[level] ?? level}>
      {level}
    </span>
  );
}
