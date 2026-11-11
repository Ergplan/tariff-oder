// Plain-English questions about DISCOM ARRs → one SQLite query over the ARR database, with an
// explanation of every part of the query: which words of the question chose it, and what was
// assumed where the question did not say.  Deterministic: the same question always gives the
// same SQL.  It never invents a figure — it only writes the query; the database answers it.

export const HEADS = [
  // [code, name, words that name it]
  ["arr", "ARR (bottom line)", ["arr", "aggregate revenue requirement", "annual revenue requirement", "revenue requirement", "net arr", "total cost", "cost to serve"]],
  ["power_purchase", "Power purchase cost", ["power purchase", "purchase of power", "pp cost", "power procurement", "cost of power", "energy purchase"]],
  ["transmission", "Transmission and SLDC charges", ["transmission", "sldc", "pgcil", "inter-state charges", "intra-state charges"]],
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

const STATES = {
  "uttar pradesh": ["UP"], "bihar": [], "himachal pradesh": ["himachal", "HP"], "jharkhand": [], "madhya pradesh": ["MP"],
  "odisha": ["orissa"], "uttarakhand": [], "delhi": [], "chhattisgarh": [], "maharashtra": ["mumbai"], "kerala": [],
  "goa and union territories": ["goa", "puducherry", "pondicherry"],
};

const q = (s) => `'${String(s).replace(/'/g, "''")}'`;
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const fy = (a) => `FY${a}-${String((a + 1) % 100).padStart(2, "0")}`;
const start = (y) => Number(y.slice(2, 6));

export function yearsIn(text) {
  const out = [];
  const add = (a) => { if (a >= 2005 && a <= 2045) { const y = fy(a); if (!out.includes(y)) out.push(y); } };
  // FY 2026-27, 2026-27, 2026/27, FY2026-2027
  for (const m of text.matchAll(/\b(?:fy\s*'?\s*)?(20\d\d)\s*[-–/]\s*(20)?(\d\d)\b/gi)) {
    if ((Number(m[1]) + 1) % 100 === Number(m[3])) add(Number(m[1]));
  }
  // FY27, FY 27 (the year ending March 2027)
  for (const m of text.matchAll(/\bfy\s*'?\s*(\d\d)\b(?!\s*[-–/])/gi)) add(2000 + Number(m[1]) - 1);
  return out;
}

function findAll(text, words) {
  return words.some((w) => new RegExp(`(^|[^a-z0-9])${esc(w.toLowerCase())}([^a-z0-9]|$)`).test(text));
}

export function translate(question, vocab) {
  const raw = question.trim();
  const text = ` ${raw.toLowerCase().replace(/[?!]/g, " ").replace(/\s+/g, " ")} `;
  const explain = [];
  const assumed = [];
  const say = (what, why) => explain.push({ what, why });

  // ---- who: discoms, states, commissions, ownership
  const discoms = [];
  for (const d of vocab.discoms) {
    const names = [d.code, d.name, ...(d.aliases || [])].filter((n) => n && n.length >= 3 && !/^(petitioner|licensee|east|west|central|state|goa)$/i.test(n));
    const hit = names.find((n) => findAll(text, [n]));
    if (hit) discoms.push({ ...d, hit });
  }
  const states = [];
  for (const [st, al] of Object.entries(STATES)) {
    const hit = [st, ...al].find((n) => (n.length <= 2 ? new RegExp(`\\b${n}\\b`).test(raw) : findAll(text, [n])));
    if (hit && !discoms.some((d) => d.state.toLowerCase() === st)) states.push({ state: vocab.states.find((s) => s.toLowerCase() === st) || st, hit });
  }
  const commissions = vocab.commissions.filter((c) => findAll(text, [c.code.toLowerCase()]));
  const ownership = /\bprivate\b/.test(text) ? "private" : /\b(state[- ]owned|government|public sector|psu)\b/.test(text) ? "state" : null;

  // ---- what: heads
  let heads = [];
  const headHits = [];
  for (const [code, name, words] of HEADS) {
    const w = [...words].sort((a, b) => b.length - a.length).find((x) => findAll(text, [x]));
    if (w) { heads.push(code); headHits.push([code, name, w]); }
  }
  // "arr" inside "share of power purchase in ARR" is the denominator, not a second head
  const share = /\b(share|percentage|per ?cent|%|proportion|as a part of)\b/.test(text) && heads.length >= 2 && heads.includes("arr");
  if (share) heads = heads.filter((h) => h !== "arr");
  // "revenue requirement" names the ARR, not revenue
  if (heads.includes("arr") && heads.includes("revenue") && !/revenue (from|at)|expected revenue|tariff revenue/.test(text)) heads = heads.filter((h) => h !== "revenue");
  // "revenue gap" names the gap
  if (heads.includes("gap") && heads.includes("revenue") && !/revenue (from|at)|expected revenue/.test(text)) heads = heads.filter((h) => h !== "revenue");
  if (heads.includes("interest_loan") && /working capital/.test(text) && !/loan/.test(text)) heads = heads.filter((h) => h !== "interest_loan");
  if (heads.includes("tax") && /tariff/.test(text) && !/income tax|\btax\b(?! ?on)/.test(text.replace(/tariff/g, ""))) heads = heads.filter((h) => h !== "tax");

  // ---- which voice and stage
  const saysClaimed = /\b(claim\w*|propos\w*|project\w*|sought|ask\w*|request\w*|petition\w*|submitted|filed|demanded)\b/.test(text);
  const saysApproved = /\b(approv\w*|allow\w*|admit\w*|sanction\w*|determin\w*|granted|passed)\b/.test(text);
  const compare = /\b(disallow\w*|cut|cuts|trimmed|reduc\w* by the commission|difference between claimed and approved|claimed vs\.? approved|claimed versus approved|approved vs\.? claimed|claimed and approved|how much less|haircut)\b/.test(text) || (saysClaimed && saysApproved);
  let voice = compare ? null : saysClaimed ? "claimed" : "approved";
  let stage = null;
  if (/\btrue[- ]?up|trued[- ]?up|truing[- ]?up|final (accounts|approval)\b/.test(text)) stage = "True-up";
  else if (/\b(apr|annual performance review|revised estimate|review year)\b/.test(text)) stage = "APR";
  else if (/\b(myt|control period|projection|projected years|future years)\b/.test(text) && !saysClaimed) stage = "MYT projection";
  else if (/\b(original(ly)? approv\w*|in the (arr|tariff) order|first approv\w*|ex[- ]ante)\b/.test(text)) stage = "ARR";
  if (/\b(earlier|previous|old) approv\w*\b/.test(text)) voice = "approved_earlier";

  // ---- when
  let years = yearsIn(raw);
  let range = null;
  const between = raw.match(/\b(?:between|from)\s+(.+?)\s+(?:and|to|till|until)\s+(.+?)(?:$|[,.?]| for | of )/i);
  if (between) {
    const a = yearsIn(between[1]), b = yearsIn(between[2]);
    if (a.length && b.length) range = [a[0], b[0]].sort();
  }
  const lastN = text.match(/\blast (\d+|two|three|four|five) (financial )?years\b/);
  const latest = /\b(latest|current|this year|most recent|newest)\b/.test(text);

  // ---- how
  const includeTotals = /\b(state total|all[- ]state|state as a whole|consolidated|combined discoms)\b/.test(text);
  const nWord = { two: 2, three: 3, four: 4, five: 5, ten: 10 };
  const topM = text.match(/\b(top|bottom|first|largest|biggest|highest|lowest|smallest)\s+(\d+|two|three|four|five|ten)\b/);
  const descRank = /\b(highest|largest|biggest|most|maximum|max|top|costliest|greatest)\b/.test(text);
  const ascRank = /\b(lowest|smallest|least|minimum|min|bottom|cheapest)\b/.test(text);
  const rank = descRank || ascRank ? (ascRank && !descRank ? "ASC" : "DESC") : null;
  const limit = topM ? (Number(topM[2]) || nWord[topM[2]]) : rank ? (/\bwhich (discom|utility|licensee|company)\b(?! ?s\b)/.test(text) && !/\bdiscoms\b/.test(text) ? 1 : 5) : null;
  const agg = /\b(total|sum|combined|altogether|aggregate of all|all together)\b/.test(text.replace(/state total|combined discoms/g, "")) && !/\btotal (revenue requirement|expenditure|cost)\b/.test(text) ? "SUM"
    : /\b(average|mean|avg)\b/.test(text) ? "AVG" : null;
  const trend = /\b(trend|over the years|over time|year[- ]?wise|by year|each year|history|historical|growth|grow|increase|change|evolution|across years)\b/.test(text) || !!range || !!lastN;

  // ---- meta questions about the database itself
  const meta = /\b(which|what|list|show|how many)\b.*\b(discoms|utilities|licensees|orders|commissions|states|documents|sources)\b/.test(text) &&
    !heads.length && !/\b(highest|lowest|largest|top)\b/.test(text);
  if (meta || /\b(coverage|what data|what is in|missing|not read|unreachable|cannot reach)\b/.test(text)) {
    return metaQuery(text, { discoms, states, commissions, say });
  }

  if (!heads.length) {
    heads = ["arr"];
    assumed.push("No cost head was named, so the query is about the ARR itself (each order's bottom-line revenue requirement).");
  }

  // ---- filters, each explained
  const where = [];
  if (discoms.length) {
    where.push(`discom IN (${discoms.map((d) => q(d.code)).join(", ")})`);
    for (const d of discoms) say(`discom = ${d.code}`, `"${d.hit}" is ${d.name} (${d.state}).`);
  }
  if (states.length) {
    where.push(`state IN (${states.map((s) => q(s.state)).join(", ")})`);
    for (const s of states) say(`state = ${s.state}`, `"${s.hit}" names the state; every DISCOM of its commission is included.`);
  }
  if (commissions.length) {
    where.push(`commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
    for (const c of commissions) say(`commission = ${c.code}`, `${c.name}.`);
  }
  if (ownership) {
    where.push(`ownership = ${q(ownership)}`);
    say(`ownership = ${ownership}`, `you asked about ${ownership === "private" ? "privately owned" : "state-owned"} DISCOMs.`);
  }
  if (!includeTotals || agg) where.push("discom <> 'TOTAL'");

  // years
  let yearNote = null;
  if (range) {
    where.push(`fiscal_year BETWEEN ${q(range[0])} AND ${q(range[1])}`);
    say(`${range[0]} to ${range[1]}`, "the years you gave, both included.");
  } else if (years.length) {
    where.push(`fiscal_year IN (${years.map(q).join(", ")})`);
    say(`fiscal_year = ${years.join(", ")}`, "the financial year(s) named in the question (April to March).");
  } else if (lastN) {
    const n = Number(lastN[1]) || nWord[lastN[1]];
    const ys = [];
    for (let a = start(vocab.latestYear); ys.length < n; a--) ys.push(fy(a));
    where.push(`fiscal_year IN (${ys.map(q).join(", ")})`);
    say(`the last ${n} years`, `${ys.slice().reverse().join(", ")}: counting back from ${vocab.latestYear}, the latest ARR year any order in the database approves.`);
  } else if (latest || (!trend && !agg && !stage)) {
    where.push(`fiscal_year = ${q(vocab.latestYear)}`);
    yearNote = vocab.latestYear;
    if (latest) say(`fiscal_year = ${vocab.latestYear}`, `"latest" is the most recent ARR year any order in the database approves.`);
    else assumed.push(`No year was given, so the query uses ${vocab.latestYear}, the most recent ARR year in the database. Add a year (e.g. FY2024-25) to change it.`);
  }

  // stage
  if (stage) {
    where.push(`stage = ${q(stage)}`);
    const why = {
      "True-up": "the trued-up figure: the Commission's final decision on that year, made two years later on audited accounts.",
      APR: "the annual performance review: the Commission's mid-year revision of the year in progress.",
      "MYT projection": "a year beyond the order's own ARR year (multi-year control period).",
      ARR: "the approval made in advance, in the order whose ARR year it is.",
    }[stage];
    say(`stage = ${stage}`, why);
  }

  const picks = (cte, voices, headList, byLabel = false) => {
    // one value per DISCOM, year, voice and head (and printed label, when listing): the newest
    // order that decides it, its main table, its first such row
    return `${cte} AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY discom, fiscal_year, voice${headList ? ", head" : ""}${byLabel ? ", label" : ""}
                               ORDER BY order_arr_year DESC, is_primary DESC, value_id) AS rn
  FROM ${headList ? "v_values" : "v_arr"}
  WHERE ${[...where, voices, headList].filter(Boolean).join("\n    AND ")}
)`;
  };

  const isArr = heads.length === 1 && heads[0] === "arr";
  const headSql = isArr ? null : `head IN (${heads.map(q).join(", ")})`;
  if (isArr) say("the ARR", "each order's bottom-line revenue requirement row (net ARR where the table prints one), chosen as recorded in arr_headline.");
  else for (const [code, name, w] of headHits.filter(([c]) => heads.includes(c))) say(`head = ${code}`, `"${w}" → ${name}; matched against each row's printed label.`);

  const dedupeNote = "When several orders decide the same year (an ARR approval, then its review, then its true-up), the newest order's figure is used: the Commission's latest word on that year.";

  let sql;
  const valueCol = isArr ? "arr_crore" : "value_crore";
  const evidence = "page, quote, label, order_title, order_url";

  if (share) {
    const h = heads[0];
    const hn = HEADS.find((x) => x[0] === h)[1];
    sql = `WITH ${picks("head_pick", `voice = ${q(voice || "approved")}`, `head = ${q(h)}`).slice(0)},
${picks("arr_pick", `voice = ${q(voice || "approved")}`, null)}
SELECT h.discom, h.fiscal_year, h.value_crore AS ${h}_crore, a.arr_crore,
       ROUND(100.0 * h.value_crore / a.arr_crore, 1) AS share_pct,
       h.page AS ${h}_page, a.page AS arr_page, h.order_title, h.order_url
FROM head_pick h JOIN arr_pick a
  ON a.discom = h.discom AND a.fiscal_year = h.fiscal_year AND a.order_id = h.order_id AND a.rn = 1
WHERE h.rn = 1 AND h.value_crore IS NOT NULL AND a.arr_crore > 0
ORDER BY share_pct ${rank || "DESC"}${limit ? `\nLIMIT ${limit}` : ""};`;
    say("share_pct = 100 × head ÷ ARR", `${hn} as a share of the ARR, both from the same order, so the two figures belong to one decision.`);
    voiceExplain(say, voice || "approved", assumed, saysClaimed || saysApproved);
  } else if (compare) {
    const hsel = isArr ? null : headSql;
    sql = `WITH ${picks("c", "voice = 'claimed'", hsel)},
${picks("a", "voice = 'approved'", hsel)}
SELECT c.discom, c.fiscal_year,${isArr ? "" : " c.head, c.label,"} c.stage,
       c.${valueCol} AS claimed_crore, a.${valueCol} AS approved_crore,
       ROUND(c.${valueCol} - a.${valueCol}, 2) AS disallowed_crore,
       ROUND(100.0 * (c.${valueCol} - a.${valueCol}) / c.${valueCol}, 1) AS disallowed_pct,
       c.page AS claimed_page, a.page AS approved_page, c.order_title, c.order_url
FROM c JOIN a ON a.discom = c.discom AND a.fiscal_year = c.fiscal_year AND a.order_id = c.order_id${isArr ? "" : " AND a.head = c.head AND a.label = c.label"} AND a.rn = 1
WHERE c.rn = 1 AND c.${valueCol} IS NOT NULL AND a.${valueCol} IS NOT NULL
ORDER BY ${rank ? `disallowed_crore ${rank}` : "c.discom, c.fiscal_year"}${limit ? `\nLIMIT ${limit}` : ""};`;
    say("claimed − approved", "the petition's figure minus the Commission's, both printed in the same order (positive: the Commission allowed less than asked).");
  } else if (agg) {
    sql = `WITH ${picks("p", `voice = ${q(voice)}`, headSql)}
SELECT fiscal_year,${isArr ? "" : " head,"} ${agg === "SUM" ? "ROUND(SUM" : "ROUND(AVG"}(${valueCol}), 2) AS ${agg === "SUM" ? "total" : "average"}_crore,
       COUNT(*) AS discoms_counted, GROUP_CONCAT(discom, ', ') AS discoms
FROM p WHERE rn = 1 AND ${valueCol} IS NOT NULL
GROUP BY fiscal_year${isArr ? "" : ", head"}
ORDER BY fiscal_year;`;
    say(agg === "SUM" ? "SUM(...)" : "AVG(...)", `${agg === "SUM" ? "added up" : "averaged"} over the DISCOMs that have a figure for that year; the DISCOMs counted are listed, because a total over missing DISCOMs is not the state's total.`);
    voiceExplain(say, voice, assumed, saysClaimed || saysApproved);
  } else {
    const cols = isArr ? `discom, discom_name, state, fiscal_year, voice, stage, arr_crore, ${evidence}`
      : `discom, discom_name, state, fiscal_year, voice, stage, head, label, value_crore, page, quote, order_title, order_url`;
    const voices = voice ? `voice = ${q(voice)}` : null;
    const orderBy = rank ? `${valueCol} ${rank}` : trend ? "discom, fiscal_year" : "discom, fiscal_year";
    sql = `WITH ${picks("p", voices, headSql, !isArr && !rank)}
SELECT ${cols}
FROM p WHERE rn = 1${rank ? ` AND ${valueCol} IS NOT NULL` : ""}
ORDER BY ${orderBy}${limit ? `\nLIMIT ${limit}` : ""};`;
    voiceExplain(say, voice, assumed, saysClaimed || saysApproved);
    if (rank) say(`ORDER BY ${valueCol} ${rank}${limit ? ` LIMIT ${limit}` : ""}`, `${rank === "DESC" ? "largest" : "smallest"} first${limit ? `, the first ${limit}` : ""}.${includeTotals ? "" : " State totals are left out so DISCOMs are ranked against DISCOMs."}`);
    if (trend) say("one row per year", "ordered by DISCOM and year so the change from year to year can be read down the table.");
  }
  if (!includeTotals && !discoms.length) assumed.push("Rows a combined order prints for the whole state (TOTAL) are left out; ask for the \"state total\" to include them.");
  assumed.push(dedupeNote);
  if (!isArr) assumed.push("A head is matched on each table row's printed label, and labels differ between commissions: read the label column before comparing DISCOMs.");
  // how many of the DISCOMs in scope the answer can speak for: a ranking or a total over the
  // DISCOMs that happen to be in the database is not a ranking or total of all of them
  const scope = [];
  if (discoms.length) scope.push(`d.code IN (${discoms.map((d) => q(d.code)).join(", ")})`);
  if (states.length) scope.push(`d.state IN (${states.map((x) => q(x.state)).join(", ")})`);
  if (commissions.length) scope.push(`d.commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
  if (ownership) scope.push(`d.ownership = ${q(ownership)}`);
  const covWhere = [...where.filter((w) => !w.startsWith("discom <>")), "discom <> 'TOTAL'",
    voice ? `voice = ${q(voice)}` : "voice IN ('claimed', 'approved')", isArr ? null : headSql].filter(Boolean);
  const coverage = {
    covered: `SELECT COUNT(DISTINCT discom) AS n FROM ${isArr ? "v_arr" : "v_values"} WHERE ${covWhere.join(" AND ")}`,
    listed: `SELECT COUNT(*) AS n FROM discoms d${scope.length ? ` WHERE ${scope.join(" AND ")}` : ""}`,
  };
  return { sql, explain, assumed, coverage, kind: share ? "share" : compare ? "compare" : agg ? "aggregate" : rank ? "rank" : "list", year: yearNote };
}

function voiceExplain(say, voice, assumed, said) {
  const why = {
    approved: "the Commission's figure (approved / admitted / allowed).",
    claimed: "the DISCOM's own figure in its petition (claimed / proposed / projected).",
    approved_earlier: "an earlier order's approval, as quoted in this order for comparison.",
  }[voice];
  if (voice) say(`voice = ${voice}`, why);
  if (!said && voice === "approved") assumed.push("You did not say claimed or approved, so the query shows what the Commission approved.");
}

function metaQuery(text, { discoms, states, commissions, say }) {
  const where = [];
  if (discoms.length) where.push(`d.code IN (${discoms.map((d) => q(d.code)).join(", ")})`);
  if (states.length) where.push(`d.state IN (${states.map((s) => q(s.state)).join(", ")})`);
  if (commissions.length) where.push(`d.commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
  const w = where.length ? `WHERE ${where.join(" AND ")}` : "";
  if (/\b(orders|documents|sources)\b/.test(text)) {
    say("orders", "every order in the database with what reading it found; read_status says whether ARR tables were found in it.");
    const ow = [];
    if (discoms.length) ow.push(`o.order_id IN (SELECT order_id FROM order_discoms WHERE discom IN (${discoms.map((d) => q(d.code)).join(", ")}))`);
    if (commissions.length) ow.push(`o.commission IN (${commissions.map((c) => q(c.code)).join(", ")})`);
    if (states.length) ow.push(`o.commission IN (SELECT code FROM commissions WHERE state IN (${states.map((s) => q(s.state)).join(", ")}))`);
    if (/not read|missing|no tables|unread/.test(text)) ow.push("o.read_status <> 'read'");
    return {
      sql: `SELECT o.commission, o.arr_year, o.title, o.read_status, o.pages,
       (SELECT COUNT(*) FROM arr_tables t WHERE t.order_id = o.order_id) AS arr_tables,
       (SELECT GROUP_CONCAT(discom, ', ') FROM order_discoms x WHERE x.order_id = o.order_id) AS discoms, o.url
FROM orders o ${ow.length ? `WHERE ${ow.join(" AND ")}` : ""}
ORDER BY o.commission, o.arr_year DESC;`, explain: [], assumed: [], kind: "meta",
    };
  }
  if (/\b(commissions|states|unreachable|cannot reach)\b/.test(text)) {
    const unreachable = /not (be )?reach|unreachable|cannot reach|could not|couldn't|blocked|missing/.test(text);
    say("commissions", `each state commission${unreachable ? " whose website this build could not reach" : ""}, whether its website was reached, and how many orders were read.`);
    return {
      sql: `SELECT c.code, c.name, c.state, CASE c.website_reachable WHEN 1 THEN 'yes' ELSE 'no' END AS website_reached,
       (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code) AS orders,
       (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code AND o.read_status = 'read') AS orders_read,
       (SELECT COUNT(DISTINCT discom) FROM arr_headline a JOIN orders o USING (order_id) WHERE o.commission = c.code AND a.discom <> 'TOTAL') AS discoms_with_arr
FROM commissions c${unreachable ? " WHERE c.website_reachable = 0" : ""} ORDER BY orders DESC, c.code;`, explain: [], assumed: [], kind: "meta",
    };
  }
  say("discoms", "each DISCOM in the reference list, with the years for which the database has an ARR figure.");
  return {
    sql: `SELECT d.code, d.name, d.state, d.ownership,
       COUNT(DISTINCT a.fiscal_year) AS years_with_arr,
       MIN(a.fiscal_year) AS first_year, MAX(a.fiscal_year) AS last_year
FROM discoms d LEFT JOIN arr_headline a ON a.discom = d.code
${w}
GROUP BY d.code ORDER BY years_with_arr DESC, d.state, d.code;`, explain: [], assumed: [], kind: "meta",
  };
}
