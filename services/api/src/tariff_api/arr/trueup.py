"""True-up and APR statements (ADR-0020): the licensee's actuals of one year set against the
commission's approval of that year, line by line, and the draft rendered from a frozen
statement.

Two kinds of number meet here and stay apart: the approved figure is a reviewed, published
ARR fact (voice ``approved``) of the order that printed it; the actual is what the licensee's
records say, entered by a named user with its source (a reviewed fact of voice ``actual``, a
page of a registered document, an unchecked statement naming a document, or, for an APR, an
estimate of the rest of the year).  The variance is the actual less the approved figure,
computed here in Decimal; it is never an amount the commission has allowed, and the draft
says so.  Totals are what was entered, never summed here; the identity checks run over the
actual column and a failing one blocks the freeze."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from .filing import WATERMARK, FilingError, Trace, _fmt, _unit_words

STATEMENT_VERSION = "trueup-1"
RENDERER_VERSION = "trueup-render-1"
KIND_WORDS = {
    "true_up": ("True-up", "final_true_up"),
    "apr": ("Annual performance review", "provisional_true_up"),
}
SOURCE_WORDS = {
    "fact": "reviewed fact of the order",
    "document": "page of a registered document (checked)",
    "statement": "statement by the client (document not seen by the application; unchecked)",
    "estimate": "estimate for the rest of the year (an assumption, not an actual)",
}


@dataclass
class ApprovedRef:
    fact_id: str
    line_code: str
    value: str
    unit: str | None
    source_id: str
    order: str
    page: int | None
    excerpt: str | None
    is_fixture: bool


@dataclass
class ActualRef:
    actual_id: str
    line_code: str
    value: str | None  # canonical; None when the unit has no conversion
    unit: str | None
    stated_value: str
    stated_unit: str
    source_kind: str
    origin: dict[str, Any]


def _variance(ap: ApprovedRef | None, ac: ActualRef | None) -> tuple[str | None, str]:
    if ac is None:
        return None, "actual_missing"
    if ac.value is None:
        return None, "actual_unconverted"
    if ap is None:
        return None, "approved_missing"
    if ap.unit != ac.unit:
        return None, "unit_mismatch"
    return format(Decimal(ac.value) - Decimal(ap.value), "f"), "complete"


def input_hash(fy: str, kind: str, approved: dict[str, ApprovedRef], actuals: dict[str, ActualRef]) -> str:
    body = {
        "v": STATEMENT_VERSION,
        "fy": fy,
        "kind": kind,
        "approved": sorted([a.fact_id, a.line_code, a.value, a.unit] for a in approved.values()),
        "actuals": sorted(
            [a.actual_id, a.line_code, a.value, a.unit, a.stated_value, a.stated_unit, a.source_kind]
            for a in actuals.values()
        ),
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def compute(
    *,
    fy: str,
    kind: str,
    approved: dict[str, ApprovedRef],
    actuals: dict[str, ActualRef],
    order: list[str],
    labels: dict[str, str],
    findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """The statement as data: rows, the identity findings over the actuals, a summary and the
    hash of every input.  ``order`` is the taxonomy order of line codes."""
    codes = sorted(set(approved) | set(actuals), key=lambda c: (order.index(c) if c in order else len(order), c))
    rows = []
    for code in codes:
        ap, ac = approved.get(code), actuals.get(code)
        variance, status = _variance(ap, ac)
        rows.append(
            {
                "line_code": code,
                "label": labels.get(code, code),
                "approved": asdict(ap) if ap else None,
                "actual": asdict(ac) if ac else None,
                "variance": variance,
                "unit": (ap.unit if ap else None) or (ac.unit if ac else None),
                "status": status,
            }
        )
    count = {
        s: sum(1 for r in rows if r["status"] == s)
        for s in ("complete", "actual_missing", "approved_missing", "unit_mismatch", "actual_unconverted")
    }
    blocking = [f for f in findings if f.get("severity") == "blocking"]
    reasons = []
    if count["actual_missing"]:
        reasons.append(f"{count['actual_missing']} approved line(s) have no actual entered")
    if count["unit_mismatch"]:
        reasons.append(f"{count['unit_mismatch']} line(s) have an actual in a different unit from the approval")
    if count["actual_unconverted"]:
        reasons.append(f"{count['actual_unconverted']} actual(s) are in a unit with no conversion")
    if blocking:
        reasons.append(f"{len(blocking)} identity check(s) fail over the actuals")
    if not approved:
        reasons.append(f"no reviewed approved figures for {fy}: read and review the order that approved {fy}")
    return {
        "version": STATEMENT_VERSION,
        "fiscal_year": fy,
        "kind": kind,
        "value_type": KIND_WORDS[kind][1],
        "rows": rows,
        "findings": findings,
        "summary": {
            **count,
            "lines": len(rows),
            "unchecked_statements": sum(1 for a in actuals.values() if a.source_kind == "statement"),
            "estimates": sum(1 for a in actuals.values() if a.source_kind == "estimate"),
            "ready": not reasons,
            "not_ready_because": reasons,
        },
        "input_hash": input_hash(fy, kind, approved, actuals),
        "note": (
            "Variance is the actual less the approved figure; it is not an amount the Commission has allowed. "
            "Totals are the figures entered, never summed by the application."
        ),
    }


# ------------------------------------------------------------------ the draft


def _approved_words(o: dict[str, Any]) -> str:
    return f"approved, {o['order']} p.{o['page']} ({o['excerpt']})"


def _actual_words(o: dict[str, Any]) -> str:
    kind = o["source_kind"]
    src = o["origin"]
    stated = f"stated {o['stated_value']} {_unit_words(o['stated_unit'])}".strip()
    if kind == "fact":
        return f"actual from a reviewed fact: {src.get('order')} p.{src.get('page')} ({stated})"
    if kind == "document":
        return (
            f'actual, {src.get("document")} p.{src.get("page")}: "{src.get("excerpt")}" ({stated}; checked on the page)'
        )
    if kind == "statement":
        return (
            f"actual stated by {src.get('entered_by')}, citing {src.get('document')}"
            f"{' p.' + str(src['page']) if src.get('page') else ''} ({stated}; NOT checked by the application): "
            f"{src.get('rationale')}"
        )
    return f"ESTIMATE by {src.get('entered_by')} ({stated}): {src.get('rationale')}"


def render(st: dict[str, Any], *, utility_code: str, utility_name: str, case_title: str, is_fixture: bool):
    """(docx, xlsx, trace summary) from a frozen statement.  Every number comes from the
    statement with a trace id; the reasons for each variance are left for the licensee."""
    from docx import Document
    from openpyxl import Workbook
    from openpyxl.comments import Comment

    if not st.get("frozen_at"):
        raise FilingError("the statement is not frozen", code="invalid_transition")
    title_word = KIND_WORDS[st["kind"]][0]
    fy = st["fiscal_year"]
    trace = Trace()
    wb = Workbook()
    ws = wb.active
    ws.title = "TU-1"
    ws.append([WATERMARK])
    ws.append([f"{title_word} of {fy}: approved and actual"])
    ws.append(["Rs crore unless stated; variance = actual less approved (not an allowed amount)"])
    ws.append(["Line", "Particulars", "Approved", "Actual", "Variance", "Unit", "Actual source"])
    table_rows = []
    for r in st["rows"]:
        code = r["line_code"]
        cells: list[Any] = [code, r["label"]]
        ids: list[str | None] = []
        ap, ac = r["approved"], r["actual"]
        if ap:
            tid = trace.add(
                f"TU-1!{code}!approved", "fact", ap["value"], ap["unit"], {**ap, "words": _approved_words(ap)}
            )
            cells.append(float(Decimal(ap["value"])))
            ids.append(tid)
        else:
            cells.append("no approved figure")
            ids.append(None)
        if ac and ac["value"] is not None:
            tid = trace.add(
                f"TU-1!{code}!actual", "actual", ac["value"], ac["unit"], {**ac, "words": _actual_words(ac)}
            )
            cells.append(float(Decimal(ac["value"])))
            ids.append(tid)
        else:
            cells.append("not entered")
            ids.append(None)
        if r["variance"] is not None:
            tid = trace.add(
                f"TU-1!{code}!variance",
                "variance",
                r["variance"],
                r["unit"],
                {"words": f"actual {ids[1]} less approved {ids[0]}", "of": [ids[1], ids[0]]},
            )
            cells.append(float(Decimal(r["variance"])))
            ids.append(tid)
        else:
            cells.append("—")
            ids.append(None)
        cells.append(_unit_words(r["unit"]))
        cells.append(SOURCE_WORDS.get(ac["source_kind"], "") if ac else "")
        ws.append(cells)
        row_no = ws.max_row
        for i, tid in enumerate(ids):
            if tid:
                c = ws.cell(row=row_no, column=3 + i)
                c.number_format = "#,##0.00"
                c.comment = Comment(f"trace {tid}", "tariff-oder")
        table_rows.append((r, ids, cells))
    ws.column_dimensions["B"].width = 44
    ws.column_dimensions["G"].width = 48

    doc = Document()
    for section in doc.sections:
        section.header.paragraphs[0].text = WATERMARK
        section.footer.paragraphs[0].text = WATERMARK
    doc.add_heading(f"{title_word} petition for {fy}: {utility_name}", level=0)
    doc.add_paragraph(WATERMARK).runs[0].bold = True
    if is_fixture:
        doc.add_paragraph("FIXTURE: synthetic data; not a real licensee or order.").runs[0].bold = True
    doc.add_paragraph(
        f"Licensee: {utility_name} ({utility_code}).  Case: {case_title}.  This draft sets the actual figures of "
        f"{fy} against those the Commission approved.  Each approved figure is a reviewed fact of the order "
        "cited; each actual is cited to its source.  The variance is the actual less the approved figure; it is "
        "not an amount the Commission has allowed, and the prudence of each variance is for the licensee to show."
    )
    unchecked = [r for r in st["rows"] if r["actual"] and r["actual"]["source_kind"] in ("statement", "estimate")]
    if unchecked:
        doc.add_heading("Figures the application could not check", level=1)
        for r in unchecked:
            ac = r["actual"]
            doc.add_paragraph(
                f"{r['label']} ({r['line_code']}): {SOURCE_WORDS[ac['source_kind']]}.", style="List Bullet"
            )
    doc.add_heading("Approved and actual", level=1)
    table = doc.add_table(rows=1, cols=6)
    for i, h in enumerate(("Line", "Particulars", "Approved", "Actual", "Variance", "Trace")):
        table.rows[0].cells[i].text = h
    for r, ids, cells in table_rows:
        row = table.add_row().cells
        row[0].text, row[1].text = r["line_code"], r["label"]
        for i in range(3):
            v = cells[2 + i]
            row[2 + i].text = _fmt(str(v)) if isinstance(v, float) else str(v)
        row[5].text = ", ".join(t for t in ids if t)
    doc.add_heading("Reasons for the variances", level=1)
    for r in st["rows"]:
        if r["variance"] is not None and Decimal(r["variance"]) != 0:
            doc.add_paragraph(
                f"{r['label']} ({r['line_code']}): [the licensee to state the reasons for the variance, "
                "whether it was controllable, and the documents that show it was prudent]"
            )
    doc.add_heading("Trace annex", level=1)
    annex = doc.add_table(rows=1, cols=4)
    for i, h in enumerate(("Trace id", "Where", "Value", "Origin")):
        annex.rows[0].cells[i].text = h
    ts = wb.create_sheet("Trace")
    ts.append([WATERMARK])
    ts.append(["Trace id", "Where", "Kind", "Value", "Unit", "Origin"])
    for e in trace.entries:
        cells = annex.add_row().cells
        cells[0].text, cells[1].text = e["id"], e["where"]
        cells[2].text = f"{e['value']} {_unit_words(e['unit'])}".strip()
        cells[3].text = e["origin"]["words"]
        ts.append([e["id"], e["where"], e["kind"], float(Decimal(e["value"])), e["unit"], e["origin"]["words"]])
    docx_buf, xlsx_buf = io.BytesIO(), io.BytesIO()
    doc.save(docx_buf)
    wb.save(xlsx_buf)
    summary = {
        "renderer": RENDERER_VERSION,
        "template": {"id": "true-up-builtin", "version": 1, "status": "builtin"},
        "statement_hash": st["input_hash"],
        "numbers": len(trace.entries),
        "by_kind": {k: sum(1 for e in trace.entries if e["kind"] == k) for k in ("fact", "actual", "variance")},
        "entries": trace.entries,
        "watermark": WATERMARK,
    }
    return docx_buf.getvalue(), xlsx_buf.getvalue(), summary
