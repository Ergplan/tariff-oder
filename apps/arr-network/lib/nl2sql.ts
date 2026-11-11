// Plain-English questions about utility ARRs -> one Postgres query over the ARR Network views
// (v_facts, v_arr, v_arr_latest), with an explanation of every part of the query: which words
// of the question chose it, and what was assumed where the question did not say.
// Ported from apps/arr-db/nl2sql.js (SQLite).  Deterministic: the same question always gives
// the same SQL.  It never invents a figure; it only writes the query and the database answers.

export const HEADS: [string, string, string[]][] = [
  ["arr", "ARR (bottom line)", ["arr", "aggregate revenue requirement", "annual revenue requirement", "revenue requirement", "net arr", "total cost", "cost to serve"]],
  ["power_purchase", "Power purchase cost", ["power purchase", "purchase of power", "pp cost", "power procurement", "cost of power", "energy purchase"]],
  ["transmission", "Transmission and SLDC charges", ["transmission charges", "transmission cost", "transmission", "sldc", "pgcil", "inter-state charges", "intra-state charges"]],
  ["om", "O&M expenses", ["o&m", "o & m", "operation and maintenance", "operations and maintenance", "o and m"]],
  ["employee", "Employee expenses", ["employee", "salary", "salaries", "staff cost", "terminal benefits", "pension"]],
  ["ag", "A&G expenses", ["a&g", "a & g", "administrative", "administration and general", "admin"]],
  ["rm", "R&M expenses", ["r&m", "r & m", "repair", "repairs and maintenance"]],
  ["depreciation", "Depreciation", ["depreciation"]],
  ["interest_loan", "Interest on loans", ["interest on loan", "interest on loans", "loan interest", "interest and finance", "interest on capital loan", "interest on long term loan"]],
  ["interest_wc", "Interest on working capital", ["working capital", "iowc"]],
  ["interest_sd", "Interest on security deposit", ["security deposit", "consumer deposit"]],
  ["roe", "Return on equity", ["return on equity", "roe", "return on capital", "equity return"]],
  ["tax", "Income tax", ["income tax", "tax"]],
  ["bad_debts", "Provision for bad debts", ["bad debt", "bad debts", "doubtful debts"]],
  ["nti", "Non-tariff income", ["non-tariff income", "non tariff income", "nti", "other income"]],
  ["revenue", "Revenue from tariff", ["revenue from tariff", "revenue at existing tariff", "expected revenue", "tariff revenue", "revenue from sale"]],
  ["gap", "Revenue gap / (surplus)", ["revenue gap", "gap", "surplus", "deficit"]],
  ["carrying_cost", "Carrying cost", ["carrying cost"]],
  ["regulatory_asset", "Regulatory asset / past gap recovery", ["regulatory asset", "true-up impact", "past gap"]],
  ["finance_charges", "Finance and bank charges", ["finance charges", "bank charges"]],
];

// Other names people use for a state (state code -> words).  Two-letter codes listed here are
// matched only in capitals, so "up" in a sentence is not Uttar Pradesh.
const STATE_ALIASES: Record<string, string[]> = {
  UP: ["UP"], MP: ["MP"], HP: ["HP", "himachal"], OD: ["orissa"], MH: ["mumbai"], PY: ["pondicherry"],
  DL: ["new delhi"], JK: ["j&k", "jammu & kashmir", "kashmir"], UK: ["uttaranchal"], TS: ["telangana"],
  AN: ["andaman"], DH: ["daman", "dadra"],
};

export interface Vocab {
  utilities: { code: string; name: string; aliases: string[]; state: string; state_name: string; commission: string; kind: string }[];
  commissions: { code: string; name: string }[];
  states: { code: string; name: string }[];
  latestYear: string;
}
export interface Explained { what: string; why: string }
export interface Translation {
  sql: string;
  explain: Explained[];
  assumed: string[];
  coverage?: { covered: string; listed: string };
  kind: "share" | "compare" | "aggregate" | "rank" | "list" | "meta";
  year?: string | null;
}

const q = (s: string) => `'${String(s).replace(/'/g, "''")}'`;
const reEsc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const fy = (a: number) => `FY${a}-${String((a + 1) % 100).padStart(2, "0")}`;
const start = (y: string) => Number(y.slice(2, 6));

export function yearsIn(text: string): string[] {
  const out: string[] = [];
  const add = (a: number) => { if (a >= 2005 && a <= 2045) { const y = fy(a); if (!out.includes(y)) out.push(y); } };
  for (const m of text.matchAll(/\b(?:fy\s*'?\s*)?(20\d\d)\s*[-–/]\s*(20)?(\d\d)\b/gi)) {
    if ((Number(m[1]) + 1) % 100 === Number(m[3])) add(Number(m[1]));
  }
  for (const m of text.matchAll(/\bfy\s*'?\s*(\d\d)\b(?!\s*[-–/])/gi)) add(2000 + Number(m[1]) - 1);
  return out;
}

/** The current financial year (April to March) on a date. */
export function currentFy(today = new Date()): string {
  const y = today.getUTCMonth() >= 3 ? today.getUTCFullYear() : today.getUTCFullYear() - 1;
  return fy(y);
}

function has(text: string, words: string[]) {
  return words.some((w) => new RegExp(`(^|[^a-z0-9])${reEsc(w.toLowerCase())}([^a-z0-9]|$)`).test(text));
}

export function translate(question: string, vocab: Vocab): Translation {
  const raw = question.trim();
  const text = ` ${raw.toLowerCase().replace(/[?!]/g, " ").replace(/\s+/g, " ")} `;
  const explain: Explained[] = [];
  const assumed: string[] = [];
  const say = (what: string, why: string) => explain.push({ what, why });

  // ---- who: utilities, states, commissions, ownership, kind of utility
  const utilities: (Vocab["utilities"][number] & { hit: string })[] = [];
  for (const d of vocab.utilities) {
    const names = [d.code, d.name, ...(d.aliases || [])].filter((n) => n && n.length >= 3 && !/^(petitioner|licensee|east|west|central|state|goa|total)$/i.test(n));
    const hit = names.find((n) => has(text, [n]));
    if (hit) utilities.push({ ...d, hit });
  }
  const states: { code: string; name: string; hit: string }[] = [];
  for (const s of vocab.states) {
    const words = [s.name, ...(STATE_ALIASES[s.code] || [])];
    const hit = words.find((n) => (/^[A-Z]{2}$/.test(n) ? new RegExp(`\\b${n}\\b`).test(raw) : has(text, [n])));
    if (hit && !utilities.some((d) => d.state === s.code)) states.push({ ...s, hit });
  }
  const commissions = vocab.commissions.filter((c) => has(text, [c.code.toLowerCase()]));
  const ownership = /\bprivate\b/.test(text) ? "private" : /\b(state[- ]owned|government|public sector|psu)\b/.test(text) ? "state" : null;
  const ukind = /\b(transcos?|transmission (utilit\w*|licensee\w*|compan\w*))\b/.test(text) ? "transco" : "discom";
  const ukindWord = ukind === "transco" ? "TRANSCO" : "DISCOM";

  // ---- what: heads
  let heads: string[] = [];
  const headHits: [string, string, string][] = [];
  for (const [code, name, words] of HEADS) {
    const w = [...words].sort((a, b) => b.length - a.length).find((x) => has(text, [x]));
    if (w) { heads.push(code); headHits.push([code, name, w]); }
  }
  if (ukind === "transco") heads = heads.filter((h) => h !== "transmission" || /transmission (charges|cost)/.test(text));
  const share = /\b(share|percentage|per ?cent|%|proportion|as a part of)\b/.test(text) && heads.length >= 2 && heads.includes("arr");
  if (share) heads = heads.filter((h) => h !== "arr");
  if (heads.includes("arr") && heads.includes("revenue") && !/revenue (from|at)|expected revenue|tariff revenue/.test(text)) heads = heads.filter((h) => h !== "revenue");
  if (heads.includes("gap") && heads.includes("revenue") && !/revenue (from|at)|expected revenue/.test(text)) heads = heads.filter((h) => h !== "revenue");
  if (heads.includes("interest_loan") && /working capital/.test(text) && !/loan/.test(text)) heads = heads.filter((h) => h !== "interest_loan");
  if (heads.includes("tax") && /tariff/.test(text) && !/income tax|\btax\b(?! ?on)/.test(text.replace(/tariff/g, ""))) heads = heads.filter((h) => h !== "tax");

  // ---- voice and stage
  const saysClaimed = /\b(claim\w*|propos\w*|project\w*|sought|ask\w*|request\w*|petition\w*|submitted|filed|demanded)\b/.test(text);
  const saysApproved = /\b(approv\w*|allow\w*|admit\w*|sanction\w*|determin\w*|granted|passed)\b/.test(text);
  const compare = /\b(disallow\w*|cut|cuts|trimmed|reduc\w* by the commission|difference between claimed and approved|claimed vs\.? approved|claimed versus approved|approved vs\.? claimed|claimed and approved|how much less|haircut)\b/.test(text) || (saysClaimed && saysApproved);
  let voice: string | null = compare ? null : saysClaimed ? "claimed" : "approved";
  let stage: string | null = null;
  if (/\btrue[- ]?up|trued[- ]?up|truing[- ]?up|final (accounts|approval)\b/.test(text)) stage = "True-up";
  else if (/\b(apr|annual performance review|revised estimate|review year)\b/.test(text)) stage = "APR";
  else if (/\b(myt|control period|projection|projected years|future years)\b/.test(text) && !saysClaimed) stage = "MYT projection";
  else if (/\b(original(ly)? approv\w*|in the (arr|tariff) order|first approv\w*|ex[- ]ante)\b/.test(text)) stage = "ARR";
  if (/\b(earlier|previous|old) approv\w*\b/.test(text)) voice = "approved_earlier";

  // ---- when
  const years = yearsIn(raw);
  let range: string[] | null = null;
  const between = raw.match(/\b(?:between|from)\s+(.+?)\s+(?:and|to|till|until)\s+(.+?)(?:$|[,.?]| for | of )/i);
  if (between) {
    const a = yearsIn(between[1]), b = yearsIn(between[2]);
    if (a.length && b.length) range = [a[0], b[0]].sort();
  }
  const lastN = text.match(/\blast (\d+|two|three|four|five) (financial )?years\b/);
  const latest = /\b(latest|current|this year|most recent|newest)\b/.test(text);

  // ---- how
  const includeTotals = /\b(state total|all[- ]state|state as a whole|consolidated|combined discoms)\b/.test(text);
  const nWord: Record<string, number> = { two: 2, three: 3, four: 4, five: 5, ten: 10 };
  const topM = text.match(/\b(top|bottom|first|largest|biggest|highest|lowest|smallest)\s+(\d+|two|three|four|five|ten)\b/);
  const descRank = /\b(highest|largest|biggest|most|maximum|max|top|costliest|greatest)\b/.test(text);
  const ascRank = /\b(lowest|smallest|least|minimum|min|bottom|cheapest)\b/.test(text);
  const rank = descRank || ascRank ? (ascRank && !descRank ? "ASC" : "DESC") : null;
  const limit = topM ? (Number(topM[2]) || nWord[topM[2]]) : rank ? (/\bwhich (discom|utility|licensee|company|transco)\b(?! ?s\b)/.test(text) && !/\b(discoms|utilities|transcos)\b/.test(text) ? 1 : 5) : null;
  const agg = /\b(total|sum|combined|altogether|aggregate of all|all together)\b/.test(text.replace(/state total|combined discoms/g, "")) && !/\btotal (revenue requirement|expenditure|cost)\b/.test(text) ? "SUM"
    : /\b(average|mean|avg)\b/.test(text) ? "AVG" : null;
  const trend = /\b(trend|over the years|over time|year[- ]?wise|by year|each year|history|historical|growth|grow|increase|change|evolution|across years)\b/.test(text) || !!range || !!lastN;

  // ---- questions about the database itself
  const meta = /\b(which|what|list|show|how many)\b.*\b(discoms|utilities|licensees|orders|commissions|states|documents|sources|transcos)\b/.test(text) &&
    !heads.length && !/\b(highest|lowest|largest|top)\b/.test(text);
  if (meta || /\b(coverage|what data|what is in|missing|not read|unreachable|cannot reach)\b/.test(text)) {
    return metaQuery(text, { utilities, states, commissions, say, ukind });
  }

  if (!heads.length) {
    heads = ["arr"];
    assumed.push("No cost head was named, so the query is about the ARR itself (each order's bottom-line revenue requirement).");
  }

  // ---- filters, each explained
  const where: string[] = [];
  if (utilities.length) {
    where.push(`utility IN (${utilities.map((d) => q(d.code)).join(", ")})`);
    for (const d of utilities) say(`utility = ${d.code}`, `"${d.hit}" is ${d.name} (${d.state_name}).`);
  }
  if (states.length) {
    const codes = states.map((s) => q(s.code)).join(", ");
    where.push(includeTotals
      ? `(state IN (${codes}) OR (utility = 'TOTAL' AND commission IN (SELECT commission FROM commission_states WHERE state IN (${codes}))))`
      : `state IN (${codes})`);
    for (const s of states) say(`state = ${s.code}`, `"${s.hit}" names ${s.name}; every utility of the state is included${includeTotals ? ", and the state totals its commission prints" : ""}.`);
  }
  if (commissions.length) {
    where.push(`commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
    for (const c of commissions) say(`commission = ${c.code}`, `${c.name}.`);
  }
  if (ownership) {
    where.push(`ownership = ${q(ownership)}`);
    say(`ownership = ${ownership}`, `you asked about ${ownership === "private" ? "privately owned" : "state-owned"} utilities.`);
  }
  if (!includeTotals || agg) {
    where.push(`utility_kind = ${q(ukind)}`);
    if (ukind === "transco") say("utility_kind = transco", "you asked about transmission utilities (TRANSCOs).");
  } else {
    where.push(`(utility_kind = ${q(ukind)} OR utility = 'TOTAL')`);
    say("state totals included", "you asked for the state total, so the TOTAL rows a combined order prints are included.");
  }

  let yearNote: string | null = null;
  if (range) {
    where.push(`fiscal_year BETWEEN ${q(range[0])} AND ${q(range[1])}`);
    say(`${range[0]} to ${range[1]}`, "the years you gave, both included.");
  } else if (years.length) {
    where.push(`fiscal_year IN (${years.map(q).join(", ")})`);
    say(`fiscal_year = ${years.join(", ")}`, "the financial year(s) named in the question (April to March).");
  } else if (lastN) {
    const n = Number(lastN[1]) || nWord[lastN[1]];
    const ys: string[] = [];
    for (let a = start(vocab.latestYear); ys.length < n; a--) ys.push(fy(a));
    where.push(`fiscal_year IN (${ys.map(q).join(", ")})`);
    say(`the last ${n} years`, `${ys.slice().reverse().join(", ")}: counting back from ${vocab.latestYear}, the latest ARR year any order in the database approves.`);
  } else if (latest || (!trend && !agg && !stage)) {
    where.push(`fiscal_year = ${q(vocab.latestYear)}`);
    yearNote = vocab.latestYear;
    if (latest) say(`fiscal_year = ${vocab.latestYear}`, `"latest" is the most recent ARR year any order in the database approves.`);
    else assumed.push(`No year was given, so the query uses ${vocab.latestYear}, the most recent ARR year in the database. Add a year (e.g. FY2024-25) to change it.`);
  }

  if (stage) {
    where.push(`stage = ${q(stage)}`);
    const why: Record<string, string> = {
      "True-up": "the trued-up figure: the Commission's final decision on that year, made two years later on audited accounts.",
      APR: "the annual performance review: the Commission's mid-year revision of the year in progress.",
      "MYT projection": "a year beyond the order's own ARR year (multi-year control period).",
      ARR: "the approval made in advance, in the order whose ARR year it is.",
    };
    say(`stage = ${stage}`, why[stage]);
  }

  const isArr = heads.length === 1 && heads[0] === "arr";
  const headSql = isArr ? null : `head IN (${heads.map(q).join(", ")})`;

  // one figure per utility, year, voice and head (and printed label, when listing): the newest
  // order that decides it.  For the ARR alone this is exactly v_arr_latest.
  const picks = (cte: string, voices: string | null, headList: string | null, byLabel = false, sameOrder = false) => {
    const conds = [...where, voices, headList].filter(Boolean).join("\n    AND ");
    if (!headList && !stage && !sameOrder) {
      return `${cte} AS (\n  SELECT *, 1 AS rn FROM v_arr_latest\n  WHERE ${conds}\n)`;
    }
    return `${cte} AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY utility, fiscal_year, voice${headList ? ", head" : ""}${byLabel ? ", label" : ""}
                               ORDER BY order_arr_year DESC NULLS LAST, fact_id DESC) AS rn
  FROM ${headList ? "v_facts" : "v_arr"}
  WHERE ${conds}
)`;
  };

  if (isArr) say("the ARR", "each order's bottom-line revenue requirement row (net ARR where the table prints one), the headline fact chosen for that order, utility, year and voice; bottom lines set aside as implausible are left out (v_arr).");
  else for (const [code, name, w] of headHits.filter(([c]) => heads.includes(c))) say(`head = ${code}`, `"${w}" -> ${name}; matched against each row's printed label.`);

  const dedupeNote = "When several orders decide the same year (an ARR approval, then its review, then its true-up), the newest order's figure is used: the Commission's latest word on that year.";
  const valueAs = isArr ? "arr_crore" : "value_crore";
  const ev = "fact_id, consensus, reviewed_by, page, quote, label, order_title, order_url";
  let sql: string;

  if (share) {
    const h = heads[0];
    const hn = HEADS.find((x) => x[0] === h)![1];
    sql = `WITH ${picks("head_pick", `voice = ${q(voice || "approved")}`, `head = ${q(h)}`)},
${picks("arr_pick", `voice = ${q(voice || "approved")}`, null, false, true)}
SELECT h.utility, h.fiscal_year, h.value_crore AS ${h}_crore, a.value_crore AS arr_crore,
       ROUND(100.0 * h.value_crore / a.value_crore, 1) AS share_pct,
       h.consensus AS ${h}_consensus, a.consensus AS arr_consensus,
       h.page AS ${h}_page, h.quote AS ${h}_quote, a.page AS arr_page, a.quote AS arr_quote,
       h.fact_id AS ${h}_fact_id, a.fact_id AS arr_fact_id, h.order_title, h.order_url
FROM head_pick h JOIN arr_pick a
  ON a.utility = h.utility AND a.fiscal_year = h.fiscal_year AND a.order_id = h.order_id AND a.rn = 1
WHERE h.rn = 1 AND h.value_crore IS NOT NULL AND a.value_crore > 0
ORDER BY share_pct ${rank || "DESC"}${limit ? `\nLIMIT ${limit}` : ""}`;
    say("share_pct = 100 x head / ARR", `${hn} as a share of the ARR, both from the same order, so the two figures belong to one decision.`);
    voiceExplain(say, voice || "approved", assumed, saysClaimed || saysApproved);
  } else if (compare) {
    const hsel = isArr ? null : headSql;
    sql = `WITH ${picks("c", "voice = 'claimed'", hsel, false, true)},
${picks("a", "voice = 'approved'", hsel, false, true)}
SELECT c.utility, c.fiscal_year,${isArr ? "" : " c.head, c.label,"} c.stage,
       c.value_crore AS claimed_crore, a.value_crore AS approved_crore,
       ROUND(c.value_crore - a.value_crore, 2) AS disallowed_crore,
       ROUND(100.0 * (c.value_crore - a.value_crore) / NULLIF(c.value_crore, 0), 1) AS disallowed_pct,
       c.consensus AS claimed_consensus, a.consensus AS approved_consensus,
       c.page AS claimed_page, c.quote AS claimed_quote, a.page AS approved_page, a.quote AS approved_quote,
       c.fact_id AS claimed_fact_id, a.fact_id AS approved_fact_id, c.order_title, c.order_url
FROM c JOIN a ON a.utility = c.utility AND a.fiscal_year = c.fiscal_year AND a.order_id = c.order_id${isArr ? "" : " AND a.head = c.head AND a.label = c.label"} AND a.rn = 1
WHERE c.rn = 1 AND c.value_crore IS NOT NULL AND a.value_crore IS NOT NULL
ORDER BY ${rank ? `disallowed_crore ${rank}` : "c.utility, c.fiscal_year"}${limit ? `\nLIMIT ${limit}` : ""}`;
    say("claimed - approved", "the petition's figure minus the Commission's, both printed in the same order (positive: the Commission allowed less than asked).");
  } else if (agg) {
    sql = `WITH ${picks("p", `voice = ${q(voice!)}`, headSql)}
SELECT fiscal_year,${isArr ? "" : " head,"} ROUND(${agg}(value_crore), 2) AS ${agg === "SUM" ? "total" : "average"}_crore,
       COUNT(*) AS utilities_counted, string_agg(utility, ', ' ORDER BY utility) AS utilities,
       string_agg(DISTINCT consensus, ', ') AS consensus_classes, COUNT(reviewed_by) AS reviewed_figures
FROM p WHERE rn = 1 AND value_crore IS NOT NULL
GROUP BY fiscal_year${isArr ? "" : ", head"}
ORDER BY fiscal_year`;
    say(agg === "SUM" ? "SUM(...)" : "AVG(...)", `${agg === "SUM" ? "added up" : "averaged"} over the ${ukindWord}s that have a figure for that year; the ${ukindWord}s counted are listed, because a total over missing ${ukindWord}s is not the state's total.`);
    voiceExplain(say, voice, assumed, saysClaimed || saysApproved);
  } else {
    const cols = isArr
      ? `utility, utility_name, state, fiscal_year, voice, stage, value_crore AS arr_crore, ${ev}`
      : `utility, utility_name, state, fiscal_year, voice, stage, head, label AS printed_label, value_crore, ${ev.replace("label, ", "")}`;
    const voices = voice ? `voice = ${q(voice)}` : null;
    const orderBy = rank ? `value_crore ${rank}` : "utility, fiscal_year";
    sql = `WITH ${picks("p", voices, headSql, !isArr && !rank)}
SELECT ${cols}
FROM p WHERE rn = 1${rank ? " AND value_crore IS NOT NULL" : ""}
ORDER BY ${orderBy}${rank ? ", utility" : ""}${limit ? `\nLIMIT ${limit}` : ""}`;
    voiceExplain(say, voice, assumed, saysClaimed || saysApproved);
    if (rank) say(`ORDER BY ${valueAs} ${rank}${limit ? ` LIMIT ${limit}` : ""}`, `${rank === "DESC" ? "largest" : "smallest"} first${limit ? `, the first ${limit}` : ""}.${includeTotals ? "" : ` State totals are left out so ${ukindWord}s are ranked against ${ukindWord}s.`}`);
    if (trend) say("one row per year", `ordered by ${ukindWord} and year so the change from year to year can be read down the table.`);
  }
  if (!includeTotals && !utilities.length) assumed.push("Rows a combined order prints for the whole state (TOTAL) are left out; ask for the \"state total\" to include them.");
  assumed.push(dedupeNote);
  if (!isArr) assumed.push("A head is matched on each table row's printed label, and labels differ between commissions: read the label before comparing utilities.");

  // How many of the utilities in scope can the answer speak for?
  const scope = [`d.kind = ${q(ukind)}`];
  if (utilities.length) scope.push(`d.code IN (${utilities.map((d) => q(d.code)).join(", ")})`);
  if (states.length) scope.push(`d.state IN (${states.map((x) => q(x.code)).join(", ")})`);
  if (commissions.length) scope.push(`d.commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
  if (ownership) scope.push(`d.ownership = ${q(ownership)}`);
  const covWhere = [...where.filter((w) => !/utility_kind|utility = 'TOTAL'/.test(w)), `utility_kind = ${q(ukind)}`,
    voice ? `voice = ${q(voice)}` : "voice IN ('claimed', 'approved')", isArr ? null : headSql].filter(Boolean);
  const coverage = {
    covered: `SELECT COUNT(DISTINCT utility) AS n FROM ${isArr ? "v_arr" : "v_facts"} WHERE ${covWhere.join(" AND ")}`,
    listed: `SELECT COUNT(*) AS n FROM utilities d WHERE ${scope.join(" AND ")}`,
  };
  return { sql, explain, assumed, coverage, kind: share ? "share" : compare ? "compare" : agg ? "aggregate" : rank ? "rank" : "list", year: yearNote };
}

function voiceExplain(say: (w: string, y: string) => void, voice: string | null, assumed: string[], said: boolean) {
  const why: Record<string, string> = {
    approved: "the Commission's figure (approved / admitted / allowed).",
    claimed: "the utility's own figure in its petition (claimed / proposed / projected).",
    approved_earlier: "an earlier order's approval, as quoted in this order for comparison.",
  };
  if (voice) say(`voice = ${voice}`, why[voice]);
  if (!said && voice === "approved") assumed.push("You did not say claimed or approved, so the query shows what the Commission approved.");
}

function metaQuery(
  text: string,
  { utilities, states, commissions, say, ukind }: {
    utilities: { code: string }[]; states: { code: string }[]; commissions: { code: string; name: string }[];
    say: (w: string, y: string) => void; ukind: string;
  },
): Translation {
  const list = (xs: { code: string }[]) => xs.map((x) => q(x.code)).join(", ");
  if (/\b(orders|documents|sources)\b/.test(text)) {
    say("orders", "every order in the database with what reading found; read_status says whether ARR tables were found in it.");
    const ow: string[] = [];
    if (utilities.length) ow.push(`o.order_id IN (SELECT order_id FROM order_utilities WHERE utility IN (${list(utilities)}))`);
    if (commissions.length) ow.push(`o.commission IN (${list(commissions)})`);
    if (states.length) ow.push(`o.commission IN (SELECT commission FROM commission_states WHERE state IN (${list(states)}))`);
    if (/not read|missing|no tables|unread/.test(text)) ow.push("o.read_status <> 'read'");
    return {
      sql: `SELECT o.order_id, o.commission, o.arr_year, o.title, o.read_status, o.pages,
       (SELECT COUNT(*) FROM parsed_tables t WHERE t.order_id = o.order_id) AS tables_read,
       (SELECT string_agg(utility, ', ' ORDER BY utility) FROM order_utilities x WHERE x.order_id = o.order_id) AS utilities, o.url
FROM orders o${ow.length ? `\nWHERE ${ow.join(" AND ")}` : ""}
ORDER BY o.commission, o.arr_year DESC NULLS LAST, o.order_id`,
      explain: [{ what: "FROM orders", why: "the order catalogue" }], assumed: [], kind: "meta",
    };
  }
  if (/\b(commissions|states|unreachable|cannot reach)\b/.test(text)) {
    const unreachable = /not (be )?reach|unreachable|cannot reach|could not|couldn't|blocked|missing/.test(text);
    say("commissions", `each state commission${unreachable ? " whose website the last Scout run could not reach" : ""}, whether its website was reached, and how many orders were read.`);
    return {
      sql: `SELECT c.code, c.name,
       (SELECT string_agg(state, ', ' ORDER BY state) FROM commission_states s WHERE s.commission = c.code) AS states,
       CASE WHEN c.website_reachable THEN 'yes' WHEN NOT c.website_reachable THEN 'no' ELSE 'not tried' END AS website_reached,
       (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code) AS orders,
       (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code AND o.read_status = 'read') AS orders_read,
       (SELECT COUNT(DISTINCT a.utility) FROM v_arr a WHERE a.commission = c.code AND a.utility <> 'TOTAL') AS utilities_with_arr
FROM commissions c${unreachable ? "\nWHERE c.website_reachable = false" : ""}
ORDER BY orders DESC, c.code`,
      explain: [{ what: "FROM commissions", why: "the commission catalogue" }], assumed: [], kind: "meta",
    };
  }
  const w: string[] = [`kind = ${q(ukind)}`];
  if (utilities.length) w.push(`utility IN (${list(utilities)})`);
  if (states.length) w.push(`state IN (${list(states)})`);
  if (commissions.length) w.push(`commission IN (${list(commissions)})`);
  say("utilities", `each ${ukind === "transco" ? "TRANSCO" : "DISCOM"} in the reference list, with its orders and the years for which the database has an ARR figure (v_coverage).`);
  return {
    sql: `SELECT utility, name, state, commission, orders, orders_read, years_with_arr, latest_approved_year
FROM v_coverage
WHERE ${w.join(" AND ")}
ORDER BY years_with_arr DESC, state, utility`,
    explain: [{ what: "FROM v_coverage", why: "coverage per utility" }], assumed: [], kind: "meta",
  };
}
