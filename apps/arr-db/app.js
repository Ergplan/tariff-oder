import { translate } from "./nl2sql.js";
import { vocabFrom } from "./vocab.js";

const $ = (id) => document.getElementById(id);
const EXAMPLES = [
  "Which discom has the highest approved ARR in FY2026-27?",
  "Approved ARR of UPCL for FY 2026-27",
  "Claimed vs approved ARR for Odisha discoms in FY2026-27",
  "How much power purchase cost did the commission disallow for MP discoms in FY 2026-27?",
  "Share of power purchase in ARR for Odisha discoms FY 2026-27",
  "Trend of approved ARR for NPCL",
  "Total approved ARR of Uttar Pradesh discoms in FY2026-27",
  "Top 5 discoms by approved return on equity in FY2025-26",
  "Trued-up ARR of JBVNL",
  "Which orders are in the database for BERC?",
  "Which commissions could not be reached?",
];
const MONEY = /(_crore|^value$)/;
let db = null;
let vocab = null;
let last = { cols: [], rows: [] };

function all(sql) {
  const res = db.exec(sql);
  if (!res.length) return [];
  const { columns, values } = res[0];
  return values.map((v) => Object.fromEntries(columns.map((c, i) => [c, v[i]])));
}

function table(el, rows, opts = {}) {
  if (!rows.length) {
    el.innerHTML = `<tbody><tr><td class="empty">No rows. The database has no figure that answers this — see Coverage for what it holds.</td></tr></tbody>`;
    return;
  }
  const cols = Object.keys(rows[0]).filter((c) => !(opts.hide || []).includes(c));
  const head = `<thead><tr>${cols.map((c) => `<th${MONEY.test(c) || /_pct$|^share|_page$|^page$|^n$|count|orders|years/.test(c) ? ' class="num"' : ""}>${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr></thead>`;
  const body = rows.map((r, i) => `<tr data-i="${i}" tabindex="0">${cols.map((c) => cell(c, r[c])).join("")}</tr>`).join("");
  el.innerHTML = head + `<tbody>${body}</tbody>`;
}

function cell(c, v) {
  if (v === null || v === undefined) return `<td class="nil">—</td>`;
  if (c === "order_url" || c === "url") return `<td><a href="${esc(v)}" target="_blank" rel="noopener">PDF</a></td>`;
  if (typeof v === "number" && (MONEY.test(c) || /_pct$|^share/.test(c))) {
    return `<td class="num">${v.toLocaleString("en-IN", { minimumFractionDigits: /_pct$|^share/.test(c) ? 1 : 2, maximumFractionDigits: 2 })}</td>`;
  }
  if (typeof v === "number") return `<td class="num">${v}</td>`;
  const s = String(v);
  return `<td${c === "quote" ? ' class="quote"' : ""}>${esc(s.length > 140 ? s.slice(0, 140) + "…" : s)}</td>`;
}

const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

function ask(question) {
  const t = translate(question, vocab);
  $("answer").hidden = false;
  $("explain").innerHTML = t.explain.length
    ? t.explain.map((e) => `<li><code>${esc(e.what)}</code> <span>${esc(e.why)}</span></li>`).join("")
    : `<li><span>A question about the database itself; the query reads its catalogue.</span></li>`;
  $("assumed").innerHTML = t.assumed.map((a) => `<li>${esc(a)}</li>`).join("");
  $("sql").value = t.sql;
  run();
  try { history.replaceState(null, "", `#q=${encodeURIComponent(question)}`); } catch { /* a sandboxed frame */ }
}

function run() {
  const sql = $("sql").value.trim();
  $("evidence").hidden = true;
  if (!/^\s*(with|select)\b/i.test(sql) || /;\s*\S/.test(sql.replace(/;\s*$/, ""))) {
    $("status").textContent = "Only one SELECT (or WITH … SELECT) statement is run.";
    return;
  }
  try {
    const t0 = performance.now();
    const rows = all(sql);
    last = { rows };
    $("status").textContent = `${rows.length} row${rows.length === 1 ? "" : "s"} in ${Math.round(performance.now() - t0)} ms`;
    $("count").textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
    table($("result"), rows, { hide: ["quote", "order_title", "discom_name", "why"] });
  } catch (e) {
    $("status").textContent = `SQL error: ${e.message}`;
    $("result").innerHTML = "";
    $("count").textContent = "";
  }
}

function showEvidence(i) {
  const r = last.rows[i];
  if (!r) return;
  const page = r.page ?? r.claimed_page ?? r.arr_page ?? r.approved_page;
  const url = r.order_url || r.url;
  const quote = r.quote;
  const parts = [];
  if (r.discom) parts.push(`<b>${esc(r.discom)}</b>${r.discom_name ? ` · ${esc(r.discom_name)}` : ""}`);
  if (r.fiscal_year) parts.push(esc(r.fiscal_year));
  if (r.voice) parts.push(esc(r.voice));
  if (r.label) parts.push(`row “${esc(r.label)}”`);
  $("evidence").innerHTML = `
    <p class="eyebrow">Where this comes from</p>
    <p>${parts.join(" · ")}</p>
    ${quote ? `<blockquote>${esc(quote)}</blockquote>` : ""}
    <p>${r.order_title ? esc(r.order_title) : ""}${page ? `, page ${page}` : ""}${url ? ` — <a href="${esc(url)}${page ? `#page=${page}` : ""}" target="_blank" rel="noopener">open the order at this page</a>` : ""}</p>
    ${r.why ? `<p class="note">Bottom line chosen: ${esc(r.why)}</p>` : ""}
    <p class="note">Machine-read from the order's text layer, not reviewed: check the page before relying on it.</p>`;
  $("evidence").hidden = false;
  $("evidence").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function csv() {
  if (!last.rows.length) return;
  const cols = Object.keys(last.rows[0]);
  const line = (vs) => vs.map((v) => (v === null || v === undefined ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))).join(",");
  const text = [line(cols), ...last.rows.map((r) => line(cols.map((c) => r[c])))].join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  a.download = "arr-query.csv";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function coverage() {
  const n = all(`SELECT (SELECT COUNT(*) FROM orders) AS orders, (SELECT COUNT(*) FROM orders WHERE read_status='read') AS read,
    (SELECT COUNT(*) FROM arr_values) AS vals, (SELECT COUNT(DISTINCT discom) FROM arr_headline WHERE discom <> 'TOTAL') AS discoms,
    (SELECT COUNT(*) FROM discoms) AS listed, (SELECT COUNT(DISTINCT commission) FROM orders WHERE read_status='read') AS comms,
    (SELECT COUNT(*) FROM commissions) AS allcomms`)[0];
  $("banner").innerHTML = `<b>${n.vals.toLocaleString("en-IN")} figures</b> from <b>${n.read}</b> orders of <b>${n.comms}</b> commissions · ARR for <b>${n.discoms}</b> of ${n.listed} listed DISCOMs · machine-read, not reviewed`;
  $("cov-intro").textContent = `${n.orders} orders were downloaded. In ${n.read} of them the reader found ARR tables; the rest are scans, annexures or layouts it does not yet read. ${n.listed} DISCOMs across ${n.allcomms} commissions are listed; ${n.discoms} have at least one ARR figure. A DISCOM with no figure is shown empty, never estimated.`;
  table($("cov-comm"), all(`SELECT c.code, c.state, CASE c.website_reachable WHEN 1 THEN 'yes' ELSE 'no' END AS website_reached,
    (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code) AS orders,
    (SELECT COUNT(*) FROM orders o WHERE o.commission = c.code AND o.read_status = 'read') AS orders_read,
    (SELECT COUNT(DISTINCT a.discom) FROM arr_headline a JOIN orders o USING (order_id) WHERE o.commission = c.code AND a.discom <> 'TOTAL') AS discoms_with_arr
    FROM commissions c ORDER BY orders DESC, c.code`));
  table($("cov-discom"), all(`SELECT d.code, d.name, d.state, d.ownership, COUNT(DISTINCT a.fiscal_year) AS years_with_arr,
    MIN(a.fiscal_year) AS first_year, MAX(a.fiscal_year) AS last_year
    FROM discoms d LEFT JOIN arr_headline a ON a.discom = d.code GROUP BY d.code ORDER BY years_with_arr DESC, d.state, d.code`));
  const info = Object.fromEntries(all("SELECT key, value FROM build_info").map((r) => [r.key, r.value]));
  const acc = info.check ? JSON.parse(info.check) : null;
  $("accuracy").innerHTML = acc
    ? `People had already read ${acc.orders_measured} of these orders row by row, recording each figure with its page. The reader was measured against those figures. Of <b>${acc.comparable_nonzero}</b> hand-read non-zero figures in tables the reader read, it found <b>${acc.found}</b> with the same number on the same page. Where the hand-read figure says whose it is, the reader agreed on claimed or approved <b>${acc.voice_agrees} of ${acc.voice_checked}</b> times, and on which DISCOM <b>${acc.licensee_agrees} of ${acc.licensee_checked}</b> times. The other ${Number(info.orders_read || 0) - acc.orders_measured} orders read have no hand-read figures, so their accuracy is <b>not measured</b>. A random sample of headline figures was looked at by eye during the build. It found layouts that were then fixed (wires-only tables taken for the whole ARR, an earlier approval taken for this order's), and more surely remain.`
    : "Not measured in this build.";
  $("foot").textContent = `Built ${info.built_on || ""} · ${info.reader || ""} · ${info.status || ""}`;
  const schema = all("SELECT name, type, sql FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type DESC, name");
  $("schema-list").innerHTML = schema.map((s) => `<details><summary><code>${esc(s.name)}</code> <span class="tag">${s.type}</span></summary><pre>${esc(s.sql)}</pre></details>`).join("");
}

async function main() {
  try {
    const SQL = await window.initSqlJs({ locateFile: (f) => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}` });
    const buf = await (await fetch("data/arr.sqlite")).arrayBuffer();
    db = new SQL.Database(new Uint8Array(buf));
  } catch (e) {
    $("banner").textContent = `The database could not be loaded (${e.message}).`;
    return;
  }
  vocab = vocabFrom(all);
  coverage();
  $("examples").innerHTML = EXAMPLES.map((e) => `<button type="button" class="chip">${esc(e)}</button>`).join("");
  $("question").disabled = $("go").disabled = false;
  const fromHash = decodeURIComponent((location.hash.match(/^#q=(.*)$/) || [])[1] || "");
  if (fromHash) { $("question").value = fromHash; ask(fromHash); }
}

$("form").addEventListener("submit", (e) => { e.preventDefault(); const v = $("question").value.trim(); if (v) ask(v); });
$("examples").addEventListener("click", (e) => { const b = e.target.closest(".chip"); if (b) { $("question").value = b.textContent; ask(b.textContent); } });
$("run").addEventListener("click", run);
$("csv").addEventListener("click", csv);
$("result").addEventListener("click", (e) => { const tr = e.target.closest("tr[data-i]"); if (tr && !e.target.closest("a")) showEvidence(Number(tr.dataset.i)); });
$("result").addEventListener("keydown", (e) => { if (e.key === "Enter") { const tr = e.target.closest("tr[data-i]"); if (tr) showEvidence(Number(tr.dataset.i)); } });
main();
