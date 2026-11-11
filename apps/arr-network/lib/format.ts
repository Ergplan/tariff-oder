export const CONSENSUS_WORDS: Record<string, string> = {
  single: "one reader",
  agreed_2: "two readers agree",
  agreed_3: "three readers agree",
  conflict: "readers disagree",
};
export const consensusWords = (c: string | null | undefined) => (c ? CONSENSUS_WORDS[c] ?? c : "");

export const VOICE_WORDS: Record<string, string> = {
  claimed: "claimed",
  approved: "approved",
  approved_earlier: "approved earlier",
  actual: "actual",
};

const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr1 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const int = new Intl.NumberFormat("en-IN");

export function crore(v: unknown): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? inr.format(n) : String(v);
}
export const pct = (v: unknown) => (v === null || v === undefined ? "—" : inr1.format(Number(v)));
export const count = (v: unknown) => (v === null || v === undefined ? "—" : int.format(Number(v)));

/** A link to the commission's own PDF at a page.  Only http(s) URLs are linked. */
export function pageLink(url: string | null | undefined, page?: number | null): string | null {
  if (!url || !/^https?:\/\//i.test(url)) return null;
  return page ? `${url.replace(/#.*$/, "")}#page=${page}` : url;
}

export function fmtDate(v: unknown): string {
  if (!v) return "—";
  const d = v instanceof Date ? v : new Date(String(v));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toISOString().slice(0, 10);
}
export function fmtTime(v: unknown): string {
  if (!v) return "—";
  const d = v instanceof Date ? v : new Date(String(v));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toISOString().slice(0, 16).replace("T", " ") + " UTC";
}

export const KIND_WORDS: Record<string, string> = { discom: "DISCOM", transco: "TRANSCO", genco: "GENCO", sldc: "SLDC" };
