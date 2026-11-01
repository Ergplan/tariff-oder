"""Filing drafts (ADR-0018, prompt rule 8): render a frozen formulation into a commission's
petition formats (XLSX) and a narrative (DOCX), each number entering only through a
placeholder that resolves to a fact, an assumption or a projection and gets a trace id.

Placeholders, in narrative text, column headers and cells:

    {fy:T0} {fy:T0-1} {fy:B}                  a year label (T0 = first target, B = base)
    {proj:CODE:T0}                            a projection line (value + unit)
    {fact:CODE:VOICE:B}                       the current reviewed fact of that voice
    {assumption:KEY:T0}                       an assumption value
    {formula:CODE}                            the words of the formula that computes the line
    {clause:CODE:T0}                          the regulation clause behind the line, if any

Refusals (``FilingError`` with code ``filing_untraced_number``): a literal digit in template
text outside a format code or a year label, a placeholder that does not resolve, a number
with no origin.  A blocked projection renders as ``[blocked: reason]``, never a number.
Every page and sheet carries the draft watermark; nothing here files anything."""

from __future__ import annotations

import io
import json
import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .formulate import fy_shift

WATERMARK = "DRAFT — prepared with software assistance; not filed"
RENDERER_VERSION = "filing-1"
_PLACEHOLDER = re.compile(r"\{([a-z]+):([^{}]+)\}")
_DIGIT = re.compile(r"\d")
_FY_LABEL = re.compile(r"FY\d{4}-\d{2}")


class FilingError(Exception):
    def __init__(self, message: str, *, code: str = "filing_untraced_number", detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


# ------------------------------------------------------------------ template (data)


class Column(BaseModel):
    model_config = ConfigDict(extra="forbid")
    header: str
    cell: str  # a placeholder with {code} standing for the row's line code, e.g. "{proj:{code}:T0}"


class Format(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9-]{0,15}$")
    title: str
    unit_note: str
    columns: list[Column]
    rows: list[str]  # line codes


class Chapter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    paragraphs: list[str]


class Template(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z]+-petition$")
    version: int = Field(ge=1)
    commission: str
    status: Literal["synthetic", "skeleton", "confirmed"]
    title: str
    formats: list[Format]
    narrative: list[Chapter]
    note: str | None = None


def templates_dir() -> Path:
    env = os.environ.get("FILING_TEMPLATES_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "filing-templates"
        if candidate.is_dir():
            return candidate
    return Path("packages/filing-templates")


@lru_cache(maxsize=16)
def load_template(commission: str, version: int | None = None) -> Template:
    """The commission's petition template, or the generic skeleton when it has none."""
    folder = templates_dir() / commission.lower()
    if not folder.is_dir() and commission.upper() != "GENERIC":
        folder = templates_dir() / "generic"
    files = []
    for p in folder.glob("petition.v*.json"):
        m = re.fullmatch(r"petition\.v(\d+)\.json", p.name)
        if m:
            files.append((int(m.group(1)), p))
    if not files:
        raise FileNotFoundError(f"no petition template for commission {commission!r}")
    chosen = max(files)[1] if version is None else next(p for v, p in files if v == version)
    return Template.model_validate(json.loads(chosen.read_text()))


# ------------------------------------------------------------------ context


@dataclass
class FactRef:
    fact_id: str
    line_code: str
    fiscal_year: str
    value_type: str
    value: str | None
    unit: str | None
    source_id: str
    source_name: str
    page_index: int | None
    excerpt: str | None


@dataclass
class ProjectionRef:
    line_code: str
    fiscal_year: str
    status: str
    value: str | None
    unit: str | None
    formula_id: str
    formula_words: str
    blocked_reason: str | None
    regulation_clause: dict[str, Any] | None
    inputs: dict[str, Any]


@dataclass
class AssumptionRef:
    assumption_id: str
    key: str
    fiscal_year: str
    value: str
    unit: str
    source_kind: str
    rationale: str
    entered_by: str
    clause_ref: dict[str, Any] | None


@dataclass
class DraftContext:
    utility_code: str
    utility_name: str
    formulation_id: str
    formulation_name: str
    base_fy: str
    targets: list[str]
    projections: dict[tuple[str, str], ProjectionRef]
    facts: dict[tuple[str, str, str], FactRef]  # (code, fy, voice)
    assumptions: dict[tuple[str, str], AssumptionRef]  # (key, fy or "")
    formula_words: dict[str, str]  # line code -> words of its formula
    labels: dict[str, str]  # line code -> taxonomy label
    is_fixture: bool


@dataclass
class Trace:
    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, where: str, kind: str, value: str, unit: str | None, origin: dict[str, Any]) -> str:
        tid = f"T{len(self.entries) + 1:04d}"
        self.entries.append({"id": tid, "where": where, "kind": kind, "value": value, "unit": unit, "origin": origin})
        return tid


def _year(ref: str, ctx: DraftContext) -> str:
    m = re.fullmatch(r"(T(\d+)|B)([+-]\d+)?", ref.strip())
    if not m:
        raise FilingError(f"bad year reference {ref!r}", code="validation_failed")
    if m.group(1) == "B":
        fy = ctx.base_fy
    else:
        idx = int(m.group(2))
        if idx >= len(ctx.targets):
            raise FilingError(f"year reference {ref!r}: the formulation has {len(ctx.targets)} target(s)")
        fy = ctx.targets[idx]
    return fy_shift(fy, int(m.group(3))) if m.group(3) else fy


def _fmt(value: str) -> str:
    d = Decimal(value)
    return f"{d:,.2f}"


def _check_literal(text: str, where: str, allowed: tuple[str, ...] = ()) -> None:
    """No number may enter a draft as literal template text."""
    stripped = _PLACEHOLDER.sub("", text)
    for a in allowed:
        stripped = stripped.replace(a, "")
    stripped = _FY_LABEL.sub("", stripped)
    if _DIGIT.search(stripped):
        raise FilingError(
            f"literal number in template text at {where}: {text[:120]!r}; numbers enter only through placeholders",
            detail={"where": where, "text": text[:200]},
        )


def resolve(
    text: str, ctx: DraftContext, trace: Trace, where: str, *, code: str | None = None
) -> tuple[str, list[str]]:
    """Text with every placeholder replaced; returns the trace ids it registered."""
    if code is not None:
        text = text.replace("{code}", code)
    _check_literal(text, where)
    ids: list[str] = []

    def repl(m: re.Match) -> str:
        kind, arg = m.group(1), m.group(2)
        parts = arg.split(":")
        if kind == "fy":
            return _year(parts[0], ctx)
        if kind == "proj":
            line, fy = parts[0], _year(parts[1], ctx)
            p = ctx.projections.get((line, fy))
            if p is None:
                raise FilingError(f"{where}: no projection {line} for {fy} in the formulation")
            if p.status == "blocked":
                return f"[blocked: {p.blocked_reason}]"
            assert p.value is not None
            ids.append(
                trace.add(
                    where,
                    "projection",
                    p.value,
                    p.unit,
                    {
                        "line_code": line,
                        "fiscal_year": fy,
                        "formula": p.formula_id,
                        "formula_words": p.formula_words,
                        "regulation_clause": p.regulation_clause,
                        "inputs": p.inputs,
                    },
                )
            )
            return f"{_fmt(p.value)} {_unit_words(p.unit)}".strip()
        if kind == "fact":
            line, voice, fy = parts[0], parts[1], _year(parts[2], ctx)
            f = ctx.facts.get((line, fy, voice))
            if f is None or f.value is None:
                return "not printed"
            ids.append(
                trace.add(
                    where,
                    "fact",
                    f.value,
                    f.unit,
                    {
                        "fact_id": f.fact_id,
                        "line_code": line,
                        "fiscal_year": fy,
                        "value_type": voice,
                        "order": f.source_name,
                        "source_id": f.source_id,
                        "page": f.page_index,
                        "excerpt": f.excerpt,
                    },
                )
            )
            return f"{_fmt(f.value)} {_unit_words(f.unit)}".strip()
        if kind == "assumption":
            key, fy = parts[0], _year(parts[1], ctx) if len(parts) > 1 else ""
            a = ctx.assumptions.get((key, fy)) or ctx.assumptions.get((key, ""))
            if a is None:
                raise FilingError(f"{where}: no assumption {key} for {fy or 'all years'}")
            ids.append(
                trace.add(
                    where,
                    "assumption",
                    a.value,
                    a.unit,
                    {
                        "assumption_id": a.assumption_id,
                        "key": key,
                        "fiscal_year": fy,
                        "source_kind": a.source_kind,
                        "entered_by": a.entered_by,
                        "rationale": a.rationale,
                        "clause_ref": a.clause_ref,
                    },
                )
            )
            return f"{a.value} {_unit_words(a.unit)}".strip()
        if kind == "formula":
            w = ctx.formula_words.get(parts[0])
            if w is None:
                raise FilingError(f"{where}: the plan has no formula for {parts[0]}")
            return w
        if kind == "clause":
            line, fy = parts[0], _year(parts[1], ctx)
            p = ctx.projections.get((line, fy))
            c = p.regulation_clause if p else None
            if not c:
                return "no regulation clause cited"
            return f"{c.get('citation') or 'clause'} of {c.get('source_name') or 'the regulation on file'}"
        raise FilingError(f"{where}: unknown placeholder kind {kind!r}", code="validation_failed")

    out = _PLACEHOLDER.sub(repl, text)
    return out, ids


def _unit_words(unit: str | None) -> str:
    return {"INR_crore": "Rs crore", "MU": "MU", "percent": "%", "INR_per_kWh": "Rs/kWh"}.get(unit or "", unit or "")


def _cell(text: str, ctx: DraftContext, trace: Trace, where: str, code: str) -> tuple[Any, str | None]:
    """A format cell: a number with its trace id, or text (``not printed``, ``[blocked: …]``)."""
    text = text.replace("{code}", code)
    _check_literal(text, where)
    m = _PLACEHOLDER.fullmatch(text.strip())
    if not m or m.group(1) not in ("proj", "fact", "assumption"):
        out, _ = resolve(text, ctx, trace, where)
        return out, None
    before = len(trace.entries)
    rendered, ids = resolve(text, ctx, trace, where)
    if ids:
        entry = trace.entries[before]
        return float(Decimal(entry["value"])), ids[0]
    return rendered, None


# ------------------------------------------------------------------ rendering


def render(template: Template, ctx: DraftContext) -> tuple[bytes, bytes, dict[str, Any]]:
    """(docx, xlsx, trace) — or ``FilingError`` before anything is written."""
    from docx import Document
    from openpyxl import Workbook
    from openpyxl.comments import Comment

    trace = Trace()
    # --- XLSX: the formats
    wb = Workbook()
    wb.remove(wb.active)
    numeric_cells: dict[tuple[str, str], str] = {}
    for fmt in template.formats:
        _check_literal(fmt.title, f"format {fmt.code} title")
        _check_literal(fmt.unit_note, f"format {fmt.code} unit note")
        ws = wb.create_sheet(fmt.code)
        ws.append([WATERMARK])
        ws.append([f"{fmt.code}: {resolve(fmt.title, ctx, trace, fmt.code + ' title')[0]}"])
        ws.append([resolve(fmt.unit_note, ctx, trace, fmt.code + " unit note")[0]])
        headers = ["Line", "Particulars"]
        for i, col in enumerate(fmt.columns):
            headers.append(resolve(col.header, ctx, trace, f"{fmt.code} column {i + 1} header")[0])
        ws.append(headers)
        for code in fmt.rows:
            label = ctx.labels.get(code, code)
            row: list[Any] = [code, label]
            cell_ids: list[str | None] = []
            for i, col in enumerate(fmt.columns):
                where = f"{fmt.code}!{code}!{i + 1}"
                v, tid = _cell(col.cell, ctx, trace, where, code)
                row.append(v)
                cell_ids.append(tid)
            ws.append(row)
            r = ws.max_row
            for i, tid in enumerate(cell_ids):
                if tid is not None:
                    c = ws.cell(row=r, column=3 + i)
                    c.number_format = "#,##0.00"
                    c.comment = Comment(f"trace {tid}", "tariff-oder")
                    numeric_cells[(fmt.code, c.coordinate)] = tid
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 48
    ts = wb.create_sheet("Trace")
    ts.append([WATERMARK])
    ts.append(["Trace id", "Where", "Kind", "Value", "Unit", "Origin"])
    # --- DOCX: the narrative
    doc = Document()
    for section in doc.sections:
        section.header.paragraphs[0].text = WATERMARK
        section.footer.paragraphs[0].text = WATERMARK
    doc.add_heading(resolve(template.title, ctx, trace, "title")[0], level=0)
    p = doc.add_paragraph(WATERMARK)
    p.runs[0].bold = True
    doc.add_paragraph(
        f"Licensee: {ctx.utility_name} ({ctx.utility_code}).  Formulation: {ctx.formulation_name}.  "
        "Template text is the template's own; numbers are placeholders resolved from reviewed facts, "
        "assumptions and projections, each listed in the trace annex."
    )
    if ctx.is_fixture:
        doc.add_paragraph("FIXTURE: synthetic data; not a real licensee or order.").runs[0].bold = True
    for ci, chapter in enumerate(template.narrative):
        doc.add_heading(resolve(chapter.title, ctx, trace, f"chapter {ci + 1} title")[0], level=1)
        for pi, para in enumerate(chapter.paragraphs):
            where = f"chapter {ci + 1} paragraph {pi + 1}"
            text, ids = resolve(para, ctx, trace, where)
            doc.add_paragraph(text + (f"  [{', '.join(ids)}]" if ids else ""))
    doc.add_heading("Trace annex", level=1)
    table = doc.add_table(rows=1, cols=5)
    for i, h in enumerate(("Trace id", "Where", "Kind", "Value", "Origin")):
        table.rows[0].cells[i].text = h
    for e in trace.entries:
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = e["id"], e["where"], e["kind"]
        cells[3].text = f"{e['value']} {_unit_words(e['unit'])}".strip()
        cells[4].text = _origin_words(e)
        ts.append([e["id"], e["where"], e["kind"], float(Decimal(e["value"])), e["unit"], _origin_words(e)])
    # --- final check: every number in a format sheet carries a trace id
    for fmt in template.formats:
        ws = wb[fmt.code]
        for row in ws.iter_rows(min_row=5):
            for c in row:
                if isinstance(c.value, int | float) and (fmt.code, c.coordinate) not in numeric_cells:
                    raise FilingError(f"untraced number {c.value} at {fmt.code}!{c.coordinate}")
    docx_buf, xlsx_buf = io.BytesIO(), io.BytesIO()
    doc.save(docx_buf)
    wb.save(xlsx_buf)
    summary = {
        "renderer": RENDERER_VERSION,
        "template": {"id": template.id, "version": template.version, "status": template.status},
        "numbers": len(trace.entries),
        "by_kind": {k: sum(1 for e in trace.entries if e["kind"] == k) for k in ("fact", "assumption", "projection")},
        "entries": trace.entries,
        "watermark": WATERMARK,
    }
    return docx_buf.getvalue(), xlsx_buf.getvalue(), summary


def _origin_words(e: dict[str, Any]) -> str:
    o = e["origin"]
    if e["kind"] == "fact":
        return (
            f"fact {o['line_code']} {o['fiscal_year']} {o['value_type']}: {o['order']} p.{o['page']} ({o['excerpt']})"
        )
    if e["kind"] == "assumption":
        src = "regulation clause" if o["source_kind"] == "regulation_clause" else "user"
        return f"assumption {o['key']} by {o['entered_by']} ({src}): {o['rationale']}"
    return f"projection {o['line_code']} {o['fiscal_year']}: {o['formula_words']}"
