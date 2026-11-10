import { SAMPLE, compute } from "./calc.js";
import { STEPS, esc } from "./steps.js";
import { UPERC, UPERC_SOURCE } from "./uperc.js";
import { METHOD } from "./method.js";
import { FORMATS } from "./formats.js";

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

function formatsHtml(id) {
  const fs = FORMATS.formats.filter((f) => f.step === id);
  const t = FORMATS.totals;
  const sum = (k) => fs.reduce((a, f) => a + f[k], 0);
  const overall =
    id === "filing"
      ? `<div class="stats">
          <div><b>${t.formats}</b><span>formats in the petition</span></div>
          <div><b>${n0(t.entered)}</b><span>figures entered by hand</span></div>
          <div><b>${n0(t.computed)}</b><span>figures worked out from them</span></div>
          <div><b>${pct1(t.agree, t.checked)}%</b><span>reproduced: ${n0(t.agree)} of ${n0(t.checked)} recomputed figures equal the filed ones</span></div>
        </div>`
      : "";
  if (!fs.length) return "";
  const rows = fs
    .map((f) => {
      const measured = f.checked
        ? `<div class="meter" title="${f.agree} of ${f.checked}"><i style="width:${(f.agree / f.checked) * 100}%"></i></div><small>${n0(f.agree)} / ${n0(f.checked)} reproduced</small>`
        : `<small>${esc(f.sameSheetAs ? "same sheet as above" : f.status === "checked" ? "nothing to recompute" : f.status)}</small>`;
      return `<details class="fmt"><summary>
          <span class="code">${esc(f.code)}</span>
          <span class="what"><b>${esc(f.title)}</b><em>${esc(f.purpose)}</em></span>
          <span class="n"><b>${n0(f.entered)}</b><small>entered</small></span>
          <span class="n"><b>${n0(f.computed)}</b><small>worked out</small></span>
          <span class="m">${measured}</span>
        </summary>
        <div class="more">${
          f.computes.length ? `<p>Worked out in this format:</p><ul>${f.computes.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : `<p>${esc(f.why || "Every figure in this format is entered; no rule computes any of them.")}</p>`
        }</div></details>`;
    })
    .join("");
  return `<h3>Evidence: the formats <span class="tag">${fs.length} of ${t.formats + t.workingSheets}</span></h3>
    <p class="sample">${esc(FORMATS.source)} ${esc(FORMATS.method)} ${esc(FORMATS.caveat)}</p>
    ${overall}
    <div class="stats small">
      <div><b>${n0(sum("entered"))}</b><span>entered in this step's formats</span></div>
      <div><b>${n0(sum("computed"))}</b><span>worked out</span></div>
      <div><b>${sum("checked") ? pct1(sum("agree"), sum("checked")) + "%" : "n/a"}</b><span>reproduced (${n0(sum("agree"))} of ${n0(sum("checked"))})</span></div>
    </div>
    <div class="fmts">${rows}</div>`;
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
    ${formatsHtml(s.id)}
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
document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-step]");
  if (a) {
    e.preventDefault();
    return go(Number(a.dataset.step));
  }
  if (e.target.id === "next") return go(current + 1);
  if (e.target.id === "prev") return go(current - 1);
  if (e.target.id === "print") return window.print();
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
