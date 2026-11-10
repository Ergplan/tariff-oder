import { SAMPLE, compute } from "./calc.js";
import { STEPS, esc } from "./steps.js";
import { UPERC, UPERC_SOURCE } from "./uperc.js";
import { METHOD } from "./method.js";
import { buildFormats, KINDS } from "./formats-sample.js";
import { workbook } from "./xlsx.js";

const KEY = "arr101.v1";
const clone = (o) => JSON.parse(JSON.stringify(o));
let state = clone(SAMPLE);
let done = {};
let current = 0;
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || "null");
  if (saved && saved.state && saved.state.categories?.length === SAMPLE.categories.length) {
    state = { ...clone(SAMPLE), ...saved.state };
    done = saved.done || {};
    current = Math.min(STEPS.length - 1, Math.max(0, saved.current | 0));
  }
} catch {
  /* storage unavailable: the page works without it */
}
const fromHash = STEPS.findIndex((s) => `#${s.id}` === location.hash);
if (fromHash >= 0) current = fromHash;

const save = () => {
  try {
    localStorage.setItem(KEY, JSON.stringify({ state, done, current }));
  } catch {
    /* ignore */
  }
};

const get = (path) => path.split(".").reduce((o, k) => o?.[k], state);
const set = (path, value) => {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => o[k], state)[last] = value;
};
const sampleOf = (path) => path.split(".").reduce((o, k) => o?.[k], SAMPLE);

const $ = (id) => document.getElementById(id);

function input(path, { kind, step, label } = {}) {
  const v = get(path);
  if (kind === "check") return `<input type="checkbox" data-path="${path}" ${v ? "checked" : ""} aria-label="${esc(label || path)}">`;
  if (kind === "text") return `<input type="text" data-path="${path}" value="${esc(v)}" aria-label="${esc(label || path)}">`;
  return `<input type="number" inputmode="decimal" step="${step || "any"}" data-path="${path}" value="${esc(v)}" aria-label="${esc(label || path)}">`;
}

const n0 = (v) => Number(v).toLocaleString("en-IN");
const pct1 = (a, b) => (b ? ((a / b) * 100).toFixed(1) : "0.0");

function methodHtml(id) {
  const m = METHOD[id] || [];
  return m.length
    ? `<h3>Method</h3><div class="method">${m.map((x) => `<div><code>${esc(x[0])}</code>${x[1] ? `<span>${esc(x[1])}</span>` : ""}</div>`).join("")}</div>`
    : "";
}

const SOURCE = {
  answers: ["From your answers", "ok"],
  illustrative: ["Partly illustrative", "warn"],
  none: ["Not in this sample", "none"],
};
const openFormats = new Set();

function cell(v, dp) {
  if (dp === null || dp === undefined) return esc(v ?? "");
  const n = Number(v);
  if (!Number.isFinite(n)) return esc(v ?? "");
  const t = Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  return n < 0 && Number(t.replace(/,/g, "")) !== 0 ? `(${t})` : t;
}

function tableHtml(t) {
  const th = t.head.map((h, i) => `<th class="${t.dp[i] != null ? "num" : ""}">${esc(h)}</th>`).join("");
  const tr = (r) => r.map((v, i) => `<td class="${t.dp[i] != null ? "num" : ""}">${cell(v, t.dp[i])}</td>`).join("");
  return `<div class="scroll"><table class="ftab"><thead><tr>${th}</tr></thead><tbody>${t.rows.map((r) => `<tr>${tr(r)}</tr>`).join("")}</tbody>${
    t.foot ? `<tfoot><tr>${t.foot.map((v, i) => `<td class="${t.dp[i] != null ? "num" : ""}">${v === null ? "" : cell(v, i ? t.dp[i] : null)}</td>`).join("")}</tr></tfoot>` : ""
  }</table></div>`;
}

function formatsHtml(id, r) {
  const fs = buildFormats(state, r).filter((f) => f.step === id);
  if (!fs.length) return "";
  return `<p class="lead">A petition is filed as a set of tables called formats. These ${fs.length} are the ones this step produces, laid out as UPERC's and filled with the sample utility's numbers. They change as you change an answer.</p>
    <div class="fmts">${fs
      .map((f) => {
        const [label, tone] = SOURCE[f.source];
        return `<details class="fmt" data-code="${esc(f.code)}" ${openFormats.has(f.code) ? "open" : ""}><summary>
            <span class="code">${esc(f.code)}</span>
            <span class="what"><b>${esc(f.title)}</b><em>${esc(f.purpose)}</em></span>
            <span class="src" data-tone="${tone}">${label}</span>
          </summary>
          <div class="more">${f.tables.map(tableHtml).join("")}${f.note ? `<p class="sample">${esc(f.note)}</p>` : ""}</div>
        </details>`;
      })
      .join("")}</div>`;
}

function download() {
  const r = compute(state);
  const F = buildFormats(state, r);
  const cover = [
    [{ b: "ARR 101: the sample utility's formats" }],
    [state.utility],
    [`ARR year ${state.arrYear}. Money in Rs lakh, energy in MWh.`],
    ["A learning example: the utility and its figures are invented. Formats marked illustrative use invented figures beyond the answers."],
    [],
    [{ b: "Format" }, { b: "Title" }, { b: "Source" }],
    ...F.map((f) => [f.code, f.title, SOURCE[f.source][0]]),
  ];
  const sheets = [{ name: "Index", rows: cover }];
  for (const f of F) {
    const rows = [[{ b: `${f.code}: ${f.title}` }], [f.purpose], []];
    for (const t of f.tables) {
      rows.push(t.head.map((h) => ({ b: h })));
      for (const x of t.rows) rows.push(x.map((v, i) => (t.dp[i] != null && Number.isFinite(Number(v)) ? Number(v) : v)));
      if (t.foot) rows.push(t.foot.map((v, i) => (i === 0 ? { b: v } : v)));
      rows.push([]);
    }
    if (f.note) rows.push([f.note]);
    sheets.push({ name: f.code, rows });
  }
  const url = URL.createObjectURL(workbook(sheets));
  const a = document.createElement("a");
  a.href = url;
  a.download = "arr-101-sample-formats.xlsx";
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderNav() {
  $("nav").innerHTML = STEPS.map(
    (s, i) =>
      `<li><a href="#${s.id}" data-step="${i}" ${i === current ? 'aria-current="step"' : ""}><span class="n">${String(i + 1).padStart(2, "0")}</span><span>${s.title}</span></a></li>`,
  ).join("");
  $("progress").style.width = `${((current + 1) / STEPS.length) * 100}%`;
}

function renderStep() {
  const s = STEPS[current];
  const qs = s.questions
    .map((q) => {
      const sample = sampleOf(q.path);
      const sampleText = q.kind === "check" ? (sample ? "yes" : "no") : `${sample}${q.unit ? " " + q.unit : ""}`;
      return `<div class="q${q.kind === "check" ? " check" : ""}">
        <label>${q.q}${q.help ? `<small>${q.help}</small>` : ""}</label>
        <div class="a">${input(q.path, { kind: q.kind, label: q.q })}${q.unit ? `<span class="unit">${q.unit}</span>` : ""}</div>
        <div class="sample">Sample answer: ${esc(sampleText)}</div>
      </div>`;
    })
    .join("");
  const grid = s.grid
    ? `<div class="scroll"><table class="grid"><thead><tr><th>Category</th>${s.grid.cols.map((c) => `<th>${c[1]}</th>`).join("")}</tr></thead><tbody>${state.categories
        .map(
          (c, i) =>
            `<tr><td>${esc(c.name)}</td>${s.grid.cols.map((col) => `<td>${input(`categories.${i}.${col[0]}`, { step: col[2], label: `${c.name}: ${col[1]}` })}</td>`).join("")}</tr>`,
        )
        .join("")}</tbody></table></div><div class="sample">The sample utility's answers are filled in. Change any figure to see the working move.</div>`
    : "";
  const sources = s.sources
    ? `<div class="scroll"><table class="grid"><thead><tr><th>Source</th><th>Share of purchase (%)</th><th>Rate (Rs/kWh)</th></tr></thead><tbody>${state.sources
        .map(
          (x, i) =>
            `<tr><td>${esc(x.name)}</td><td>${input(`sources.${i}.sharePct`, { label: `${x.name}: share` })}</td><td>${input(`sources.${i}.rate`, { label: `${x.name}: rate` })}</td></tr>`,
        )
        .join("")}</tbody></table></div>`
    : "";
  const points = s.points ? `<dl class="points">${s.points.map((p) => `<dt>${p[0]}</dt><dd>${p[1]}</dd>`).join("")}</dl>` : "";
  const checklist = s.checklist
    ? `<ul class="checklist">${s.checklist
        .map((c, i) => `<li><label><input type="checkbox" data-done="${i}" ${done[i] ? "checked" : ""}> <span>${c}</span></label></li>`)
        .join("")}</ul><p class="sample" id="doneCount"></p>`
    : "";
  const hasQuestions = qs || grid || sources;
  $("step").innerHTML = `
    <p class="eyebrow">Step ${String(current + 1).padStart(2, "0")} / ${STEPS.length}</p>
    <h2>${s.title}</h2>
    <p class="plain">${s.plain}</p>
    ${points}
    ${methodHtml(s.id)}
    ${hasQuestions ? `<h3>Questions to answer</h3>${sources}${grid}${qs}` : ""}
    ${checklist}
    <div id="workingWrap"><h3>The working</h3><div id="working"></div></div>
    <h3>Your formats <span class="tag">all ${KINDS} kinds</span></h3>
    <div id="formats"></div>
    <p><button type="button" id="xlsx">Download all ${KINDS} formats (.xlsx)</button></p>
    <h3>UPERC check <span class="tag">Uttar Pradesh</span></h3>
    <p class="sample">What the ${UPERC_SOURCE.title} say for this step, with the regulation and page. ${UPERC_SOURCE.status}</p>
    <div id="uperc"></div>
    <h3>Watch out</h3>
    <ul class="watch">${s.watch.map((w) => `<li>${w}</li>`).join("")}</ul>
    <div class="pager">
      <button type="button" id="prev" ${current === 0 ? "disabled" : ""}>Back</button>
      ${current === STEPS.length - 1 ? `<button type="button" id="print" class="primary">Print this guide's result</button>` : `<button type="button" id="next" class="primary">Next — ${STEPS[current + 1].title}</button>`}
    </div>`;
  renderWorking();
}

function renderWorking() {
  const r = compute(state);
  const html = STEPS[current].working(r, state);
  $("workingWrap").hidden = !html;
  $("working").innerHTML = html;
  // keep open tables open across the redraw: read the state from the page itself
  for (const d of document.querySelectorAll("#formats .fmt")) d.open ? openFormats.add(d.dataset.code) : openFormats.delete(d.dataset.code);
  $("formats").innerHTML = formatsHtml(STEPS[current].id, r);
  $("uperc").innerHTML = (UPERC[STEPS[current].id] || [])
    .map((c) => {
      const res = c.check ? c.check(state, r) : null;
      const tone = res ? (res.ok === true ? "ok" : res.ok === false ? "bad" : "note") : "";
      const label = { ok: "Matches", bad: "Differs", note: "Note" }[tone];
      return `<div class="reg"><div class="cite">Reg. ${c.reg}<small>page ${c.page}</small></div><div><p>${esc(c.says)}</p><blockquote>“${esc(c.quote)}”</blockquote>${
        res ? `<p class="verdict" data-tone="${tone}"><b>${label}:</b> ${esc(res.text)}</p>` : ""
      }</div></div>`;
    })
    .join("");
  $("sumArr").textContent = r.arr.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  $("sumRev").textContent = r.revenue.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  $("sumGap").textContent = r.totalGap.toLocaleString("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  $("sumAcos").textContent = r.acos.toFixed(2);
  const dc = $("doneCount");
  if (dc) dc.textContent = `${Object.values(done).filter(Boolean).length} of ${STEPS[current].checklist.length} checked.`;
}

function go(i) {
  current = Math.min(STEPS.length - 1, Math.max(0, i));
  history.replaceState(null, "", `#${STEPS[current].id}`);
  save();
  renderNav();
  renderStep();
  $("step").focus({ preventScroll: true });
  window.scrollTo({ top: 0 });
}

document.addEventListener("input", (e) => {
  const t = e.target;
  if (t.dataset?.path) {
    const kind = t.type;
    set(t.dataset.path, kind === "checkbox" ? t.checked : kind === "number" ? (t.value === "" ? 0 : Number(t.value)) : t.value);
    save();
    renderWorking();
  } else if (t.dataset?.done !== undefined) {
    done[t.dataset.done] = t.checked;
    save();
    renderWorking();
  }
});
document.addEventListener(
  "toggle",
  (e) => {
    const d = e.target;
    if (d.classList?.contains("fmt")) d.open ? openFormats.add(d.dataset.code) : openFormats.delete(d.dataset.code);
  },
  true,
);
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-step]");
  if (a) {
    e.preventDefault();
    return go(Number(a.dataset.step));
  }
  if (e.target.id === "next") return go(current + 1);
  if (e.target.id === "prev") return go(current - 1);
  if (e.target.id === "print") return window.print();
  if (e.target.id === "xlsx") return download();
  if (e.target.id === "reset") {
    state = clone(SAMPLE);
    done = {};
    save();
    renderStep();
  }
});

// a link to a step (#capital) works without a reload
window.addEventListener("hashchange", () => {
  const i = STEPS.findIndex((x) => `#${x.id}` === location.hash);
  if (i >= 0 && i !== current) go(i);
});

renderNav();
renderStep();
