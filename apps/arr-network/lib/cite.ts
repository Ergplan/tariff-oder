import { consensusWords, crore, VOICE_WORDS } from "./format.ts";

export interface FactRow {
  fact_id: number; utility: string; utility_name: string | null; state: string | null; state_name: string | null; commission: string;
  commission_name?: string | null; fiscal_year: string; voice: string; stage: string | null; head: string; head_name: string;
  label: string; value_crore: number | null; value: number; unit: string | null; page: number; quote: string;
  consensus: string; readers: string[]; reviewed_by: string | null; reviewed_at: Date | string | null; order_id: number;
  order_title: string; order_url: string; order_arr_year: string | null; order_date?: Date | string | null;
}

export function amount(f: FactRow): string {
  return f.value_crore !== null && f.value_crore !== undefined ? `Rs ${crore(f.value_crore)} crore` : `${crore(f.value)}${f.unit ? ` ${f.unit}` : " (unit not printed)"}`;
}

function trust(f: FactRow): string {
  const r = `${consensusWords(f.consensus)} (${(f.readers || []).join(", ")})`;
  return f.reviewed_by ? `Machine-read, ${r}; reviewed by a person (${f.reviewed_by})` : `Machine-read, ${r}; not reviewed by a person`;
}

export function citationText(f: FactRow, permalink: string, accessed: string): string {
  const who = f.utility === "TOTAL" ? `${f.state_name ?? f.commission} state total` : `${f.utility_name ?? f.utility} (${f.utility})`;
  return `${who}, ${f.fiscal_year}, ${VOICE_WORDS[f.voice] ?? f.voice}${f.stage ? ` (${f.stage})` : ""}, ${f.head_name}: ${amount(f)}, ` +
    `printed as "${f.label}". ${f.commission_name ?? f.commission}, "${f.order_title}", p. ${f.page}. ${f.order_url}#page=${f.page}. ` +
    `${trust(f)}. ARR Network, figure ${f.fact_id}, ${permalink} (accessed ${accessed}).`;
}

/** Escape text for a BibTeX field value in braces. */
export function bibEscape(s: string): string {
  return s
    .replace(/\\/g, "\\textbackslash{}")
    .replace(/([{}%&$#_])/g, "\\$1")
    .replace(/~/g, "\\textasciitilde{}")
    .replace(/\^/g, "\\textasciicircum{}")
    .replace(/[\r\n]+/g, " ");
}

export function bibtex(f: FactRow, permalink: string, accessed: string): string {
  const year = f.order_date ? String(f.order_date instanceof Date ? f.order_date.toISOString() : f.order_date).slice(0, 4) : null;
  const fields: [string, string][] = [
    ["title", `${f.order_title}: ${f.head_name}, ${f.utility}, ${f.fiscal_year} (${f.voice})`],
    ["author", `{${f.commission_name ?? f.commission}}`],
    ...(year ? [["year", year] as [string, string]] : []),
    ["howpublished", `\\url{${f.order_url}#page=${f.page}}`],
    ["note", `p. ${f.page}; printed as "${f.label}": ${amount(f)}. ${trust(f)}. Quote: "${f.quote}"`],
    ["url", permalink],
    ["urldate", accessed],
  ];
  const body = fields.map(([k, v]) => {
    const raw = k === "howpublished" || k === "url" || k === "author";
    const val = raw ? (k === "author" ? `{${bibEscape(v.slice(1, -1))}}` : v.replace(/[{}]/g, (c) => (k === "url" ? encodeURIComponent(c) : c))) : bibEscape(v);
    return `  ${k} = {${val}}`;
  }).join(",\n");
  return `@misc{arrnet-fact-${f.fact_id},\n${body}\n}`;
}
